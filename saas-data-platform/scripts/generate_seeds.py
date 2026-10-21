#!/usr/bin/env python
"""
generate_seeds.py — Deterministic synthetic data generator for the revenue
domain of the SaaS data platform (Salesforce CRM + NetSuite ERP + usage).
The people domain has its own generator, generate_people_seeds.py.

Everything here is *synthetic* (Faker + a fixed random seed), so the output is
safe to publish. Re-running always produces byte-identical CSVs, which keeps
`dbt build` and the data tests reproducible.

What it models
--------------
A B2B SaaS revenue stack with two source systems:

  * Salesforce (CRM)  -> accounts, users, products, opportunities + line items,
                         contracts, subscriptions  (the ARR source of truth)
  * NetSuite (ERP)    -> customers, items, sales orders + lines, invoices + lines

The generator simulates realistic go-to-market *motions* per account
(land -> renew -> upsell / cross-sell / downgrade -> churn) so that the
downstream revenue categories emerge from the data rather than being hard-coded:

    new_logo · upsell · cross_sell · downgrade · churn · scheduled

Deals are priced off regional price books and discounted (CPQ), with their own
random generator so pricing never changes which deals happen or when. Every deal
gets quotes (drafts, then one primary quote that ties to the booking to the
cent), and discounts above 25% need an approval. A few are seeded to close
without one, for the approvals report to find.

It also injects a controlled number of Salesforce<->NetSuite discrepancies
(amount mismatches, missing orders, orphan orders, timing differences, currency
rounding, partial billing) so the reconciliation mart has something to surface.
The seeded counts are printed and written to scripts/seeded_discrepancy_counts.json
so the dbt tests can assert them.

Run:  python scripts/generate_seeds.py
"""
import os
import json
import random
import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
from faker import Faker

# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker("en_US")
Faker.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SF_DIR = os.path.join(ROOT, "seeds", "salesforce")
NS_DIR = os.path.join(ROOT, "seeds", "netsuite")
USE_DIR = os.path.join(ROOT, "seeds", "usage")
for _d in (SF_DIR, NS_DIR, USE_DIR):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------- #
# Calendar — 36 monthly ARR measurement periods (Jan 2023 .. Dec 2025)
# --------------------------------------------------------------------------- #
BASE_YEAR, BASE_MONTH = 2023, 1
LAST_IDX = 35  # 2025-12 (inclusive)


def month_start(i: int) -> datetime.date:
    y = BASE_YEAR + (BASE_MONTH - 1 + i) // 12
    m = (BASE_MONTH - 1 + i) % 12 + 1
    return datetime.date(y, m, 1)


def month_end(i: int) -> datetime.date:
    s = month_start(i)
    nxt = datetime.date(s.year + (s.month == 12), (s.month % 12) + 1, 1)
    return nxt - datetime.timedelta(days=1)


def iso(d: datetime.date) -> str:
    return d.isoformat()


def money(x: float) -> float:
    return round(float(x), 2)


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
GEOS = {
    "NA": ["United States", "Canada"],
    "EMEA": ["United Kingdom", "Germany", "France", "Netherlands", "Sweden"],
    "APAC": ["Australia", "Japan", "Singapore", "India"],
    "LATAM": ["Brazil", "Mexico"],
}
GEO_CURRENCY = {"NA": "USD", "EMEA": "EUR", "APAC": "USD", "LATAM": "USD"}
DIVISIONS = ["Enterprise", "Commercial", "Public Sector"]
INDUSTRIES = [
    "Technology", "Financial Services", "Healthcare", "Retail", "Manufacturing",
    "Media", "Telecommunications", "Energy", "Education", "Government",
]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
SALES_TEAMS = ["Enterprise", "Commercial", "Strategic"]

# Product catalog: (sku, line_of_business, product_family, product_name,
#                   is_recurring, annual_unit_list_price)
PRODUCTS = [
    ("ANL-CLOUD",   "Core Platform",        "Analytics",   "Analytics Cloud",           True,  18000),
    ("ANL-SELF",    "Core Platform",        "Analytics",   "Analytics Self-Hosted",     True,  15000),
    ("AUT-CLOUD",   "Core Platform",        "Automation",  "Automation Cloud",          True,  22000),
    ("AUT-ENT",     "Core Platform",        "Automation",  "Automation Enterprise",     True,  30000),
    ("INT-CLOUD",   "Core Platform",        "Integrations","Integrations Hub",          True,  16000),
    ("INT-ENT",     "Core Platform",        "Integrations","Integrations Enterprise",   True,  28000),
    ("SEC-AUDIT",   "Security & Compliance","Audit",       "Audit Log",                 True,  12000),
    ("SEC-ACCESS",  "Security & Compliance","Access",      "Access Governance",         True,  14000),
    ("ENT-SUITE",   "Core Platform",        "Suite",       "Enterprise Suite",          True,  95000),
    ("PS-IMPL",     "Professional Services","Onboarding",  "Implementation Services",   False, 25000),
    ("PS-TRAIN",    "Professional Services","Training",    "Training Package",          False, 8000),
    ("PS-MIGR",     "Professional Services","Migration",   "Migration Services",        False, 18000),
]
RECURRING_PIDS = [p[0] for p in PRODUCTS if p[4]]
ONETIME_PIDS = [p[0] for p in PRODUCTS if not p[4]]
PRICE = {p[0]: p[5] for p in PRODUCTS}

# --------------------------------------------------------------------------- #
# Pricing (CPQ). List prices come from a price book per region, rising each
# year; each deal is discounted off list. Pricing draws from its OWN generator,
# so every account, deal and date in the simulation is unchanged by it.
# --------------------------------------------------------------------------- #
price_rng = random.Random(2024)
LIST_MARKUP = 1.25                 # list sits above the typical net price
LIST_GROWTH = 0.05                 # list prices rise 5% a year
REGION_LIST = {"NA": 1.00, "EMEA": 1.00, "APAC": 0.95, "LATAM": 0.90}
SEGMENT_DISCOUNT = {"SMB": 0.10, "Mid-Market": 0.16, "Enterprise": 0.22}
NEW_BUSINESS_EXTRA = 0.03
QUARTER_END_EXTRA = 0.06           # seeded finding: last month of each quarter discounts deeper
HEAVY_DISCOUNTER_EXTRA = 0.08      # seeded finding: two reps discount deeper than the rest
SERVICES_MAX_DISCOUNT = 0.10
APPROVAL_THRESHOLD = 0.25          # new pricing above 25% off list needs a Sales VP...
CFO_THRESHOLD = 0.35               # ...and above 35%, the CFO
UNAPPROVED_SEEDED = 9              # seeded finding: deals over the threshold closed without approval
N_LOST = 650                       # lost deals, for a realistic win rate on new pricing (~40%)


def year_of(idx: int) -> int:
    return BASE_YEAR + (BASE_MONTH - 1 + idx) // 12


def list_price(pid: str, region: str, year: int) -> float:
    return float(round(PRICE[pid] * LIST_MARKUP * REGION_LIST[region] * (1 + LIST_GROWTH) ** (year - 2023)))

N_ACCOUNTS = 200
N_USERS = 25

# --------------------------------------------------------------------------- #
# ID helpers
# --------------------------------------------------------------------------- #
_counters = defaultdict(int)


def nid(prefix: str, width: int = 5) -> str:
    _counters[prefix] += 1
    return f"{prefix}-{_counters[prefix]:0{width}d}"


# --------------------------------------------------------------------------- #
# 1) Users (sales reps) and 2) Products
# --------------------------------------------------------------------------- #
users = []
for _ in range(N_USERS):
    region = random.choice(list(GEOS.keys()))
    users.append({
        "user_id": nid("USR", 3),
        "user_name": fake.name(),
        "sales_team": random.choice(SALES_TEAMS),
        "sales_region": region,
        "role": "Account Executive",
    })
users_by_region = defaultdict(list)
for u in users:
    users_by_region[u["sales_region"]].append(u["user_id"])

REP_OFFSET = {u["user_id"]: price_rng.gauss(0, 0.02) for u in users}
HEAVY_DISCOUNTERS = sorted(price_rng.sample([u["user_id"] for u in users], 2))
for _uid in HEAVY_DISCOUNTERS:
    REP_OFFSET[_uid] += HEAVY_DISCOUNTER_EXTRA


def deal_discount(acct, opp_type, idx):
    """A deal's discount off list: segment, deal type, the rep's habit, quarter-end pressure."""
    d = SEGMENT_DISCOUNT[acct["segment"]] + REP_OFFSET[acct["owner_id"]]
    if opp_type == "New Business":
        d += NEW_BUSINESS_EXTRA
    if idx is not None and month_start(idx).month in (3, 6, 9, 12):
        d += QUARTER_END_EXTRA
    d += price_rng.gauss(0, 0.03)
    return round(min(0.45, max(0.0, d)), 3)


def net_price(pid, acct, idx, discount):
    return round(list_price(pid, acct["geo_region"], year_of(idx)) * (1 - discount), 2)


def unit_of(seg):
    return round(seg["arr"] / seg["seats"], 2)

products = []
for sku, lob, family, name, is_rec, price in PRODUCTS:
    products.append({
        "product_id": sku,
        "product_name": name,
        "product_sku": sku,
        "line_of_business": lob,
        "product_family": family,
        "product_category": "Recurring" if is_rec else "One-Time",
        "is_recurring": int(is_rec),
        "is_active": 1,
        "list_unit_price": round(price * LIST_MARKUP),
    })

# --------------------------------------------------------------------------- #
# 3) Accounts
# --------------------------------------------------------------------------- #
accounts = []
for i in range(N_ACCOUNTS):
    geo = random.choices(list(GEOS.keys()), weights=[50, 30, 15, 5])[0]
    country = random.choice(GEOS[geo])
    # ~12% of accounts transact in a non-USD currency (drives FX recon cases)
    currency = GEO_CURRENCY[geo] if (geo == "EMEA" and random.random() < 0.8) else "USD"
    if geo == "EMEA" and random.random() < 0.15:
        currency = "GBP"
    segment = random.choices(SEGMENTS, weights=[30, 45, 25])[0]
    division = ("Public Sector" if random.random() < 0.12
                else ("Enterprise" if segment == "Enterprise" else "Commercial"))
    owner = random.choice(users_by_region.get(geo) or [u["user_id"] for u in users])
    accounts.append({
        "account_id": nid("ACC", 4),
        "account_name": fake.company(),
        "industry": random.choice(INDUSTRIES),
        "billing_country": country,
        "geo_region": geo,
        "division": division,
        "segment": segment,
        "account_tier": {"Enterprise": "Tier 1", "Mid-Market": "Tier 2", "SMB": "Tier 3"}[segment],
        "account_currency": currency,
        "owner_id": owner,
        "created_date": iso(month_start(random.randint(0, 6)) - datetime.timedelta(days=random.randint(30, 400))),
        "is_customer": 0,  # flipped to 1 below if the account ever lands a deal
    })
acct_by_id = {a["account_id"]: a for a in accounts}

# --------------------------------------------------------------------------- #
# Output collectors
# --------------------------------------------------------------------------- #
opps, opp_lines = [], []
contracts, subscriptions = [], []
segments = []  # (account_id, product_id, start_idx, end_idx, seats, arr, sub_id, contract_id)
ns_orders, ns_order_lines = [], []
ns_invoices, ns_invoice_lines = [], []
usage_rows = []

# order rows are kept addressable by contract so we can inject discrepancies later
order_by_contract = {}


def make_opp(account_id, owner_id, opp_type, idx, lines, is_won, term_months, currency,
             contract_id=None, is_pipeline=False, close_idx=None):
    """Create an opportunity header + its line items.

    `lines` is a list of dicts: product_id, quantity, unit_price, is_recurring,
    line_amount (the ACV contribution: annualized recurring delta, or one-time fee).
    """
    opp_id = nid("OPP", 6)
    amount = money(sum(l["line_amount"] for l in lines))
    if is_pipeline:
        stage = random.choice(["Prospecting", "Qualification", "Proposal", "Negotiation"])
        forecast = random.choice(["Pipeline", "Best Case", "Commit"])
        is_closed = 0
        close_d = month_start(0).replace(year=2026, month=random.randint(7, 12), day=random.randint(1, 28))
    else:
        is_closed = 1
        if is_won:
            stage, forecast = "Closed Won", "Closed"
        else:
            stage, forecast = "Closed Lost", "Omitted"
        ci = close_idx if close_idx is not None else idx
        close_d = month_start(ci) + datetime.timedelta(days=random.randint(0, 26))
    created_d = close_d - datetime.timedelta(days=random.randint(25, 120))
    opps.append({
        "opportunity_id": opp_id,
        "account_id": account_id,
        "owner_id": owner_id,
        "opportunity_name": f"{acct_by_id[account_id]['account_name']} - {opp_type}",
        "opportunity_type": opp_type,
        "stage_name": stage,
        "forecast_category": forecast,
        "amount": amount,
        "currency_code": currency,
        "term_months": term_months,
        "created_date": iso(created_d),
        "close_date": iso(close_d),
        "is_closed": is_closed,
        "is_won": int(is_won),
        "contract_id": contract_id or "",
    })
    for l in lines:
        opp_lines.append({
            "opportunity_line_id": nid("OLI", 6),
            "opportunity_id": opp_id,
            "product_id": l["product_id"],
            "quantity": l["quantity"],
            "unit_price": money(l["unit_price"]),
            "term_months": term_months,
            "is_recurring": int(l["is_recurring"]),
            "line_amount": money(l["line_amount"]),
        })
    return opp_id


def make_contract_and_order(account_id, idx, term_months, tcv, currency):
    """Create a Salesforce contract and its mirrored NetSuite sales order."""
    contract_id = nid("CTR", 5)
    order_ref = nid("ORDREF", 5)
    start = month_start(idx)
    end = month_end(min(LAST_IDX + 60, idx + term_months - 1))
    contracts.append({
        "contract_id": contract_id,
        "account_id": account_id,
        "contract_number": contract_id.replace("CTR", "C"),
        "start_date": iso(start),
        "end_date": iso(end),
        "term_months": term_months,
        "contract_status": "Active" if (idx + term_months - 1) >= LAST_IDX else "Expired",
        "currency_code": currency,
        "external_order_ref": order_ref,
        "total_contract_value": money(tcv),
    })
    # mirrored NetSuite order (happy path; discrepancies injected afterwards)
    order_id = nid("NSO", 5)
    order_by_contract[contract_id] = {
        "sales_order_id": order_id,
        "ns_customer_id": ns_customer_of[account_id],
        "order_number": order_id.replace("NSO", "SO"),
        "external_order_ref": order_ref,
        "order_date": iso(start + datetime.timedelta(days=random.randint(0, 4))),
        "order_status": "Billed",
        "order_total": money(tcv),
        "currency_code": currency,
        "_start_idx": idx,
    }
    return contract_id, order_ref


# NetSuite customers + items mirror Salesforce accounts + products via external IDs
ns_customer_of = {}
ns_customers, ns_items = [], []
for a in accounts:
    cid = nid("NSC", 4)
    ns_customer_of[a["account_id"]] = cid
    ns_customers.append({
        "ns_customer_id": cid,
        "customer_name": a["account_name"],
        "sfdc_account_external_id": a["account_id"],
        "subsidiary": {"NA": "SaaSCo Inc", "EMEA": "SaaSCo EMEA Ltd",
                       "APAC": "SaaSCo APAC Pte", "LATAM": "SaaSCo Inc"}[a["geo_region"]],
        "currency_code": a["account_currency"],
    })
ns_item_of = {}
for p in products:
    iid = nid("NSI", 3)
    ns_item_of[p["product_id"]] = iid
    ns_items.append({
        "ns_item_id": iid,
        "item_name": p["product_name"],
        "item_type": "Service" if p["is_recurring"] else "OtherCharge",
        "sfdc_product_external_id": p["product_id"],
    })

# --------------------------------------------------------------------------- #
# 4) Simulate per-account GTM lifecycle
# --------------------------------------------------------------------------- #
TERMS = [12, 12, 12, 24, 36]


def seats_for(pid):
    return random.randint(1, 12)


def recurring_line(pid, seats, unit, line_amount=None):
    amt = round(seats * unit, 2) if line_amount is None else line_amount
    return {"product_id": pid, "quantity": seats, "unit_price": unit,
            "is_recurring": True, "line_amount": amt}


def line_tcv(line, term_months):
    """TCV contribution of an opportunity line (recurring annualized over the term)."""
    if line["is_recurring"]:
        return line["line_amount"] * (term_months / 12.0)
    return line["line_amount"]


for a in accounts:
    aid = a["account_id"]
    owner = a["owner_id"]
    currency = a["account_currency"]
    landing = random.randint(0, 30)
    owned = {}  # product_id -> dict(seats, arr, start_idx, sub_id, contract_id)

    def open_seg(pid, idx, seats, contract_id, arr):
        owned[pid] = {"seats": seats, "arr": round(arr, 2), "start_idx": idx,
                      "sub_id": nid("SUB", 5), "contract_id": contract_id}

    def close_seg(pid, end_idx):
        o = owned.pop(pid)
        segments.append({
            "subscription_id": o["sub_id"], "contract_id": o["contract_id"],
            "account_id": aid, "product_id": pid, "seats": o["seats"], "arr": o["arr"],
            "start_idx": o["start_idx"], "end_idx": end_idx,
        })

    # ---- Landing (New Business) ----
    a["is_customer"] = 1
    term = random.choice(TERMS)
    n_init = random.choices([1, 2, 3], weights=[45, 40, 15])[0]
    init_pids = random.sample(RECURRING_PIDS, n_init)
    d = deal_discount(a, "New Business", landing)
    lines = [recurring_line(pid, seats_for(pid), net_price(pid, a, landing, d)) for pid in init_pids]
    if random.random() < 0.5:  # ~half of landings attach a one-time services line
        otp = random.choice(ONETIME_PIDS)
        fee = net_price(otp, a, landing, min(d, SERVICES_MAX_DISCOUNT))
        lines.append({"product_id": otp, "quantity": 1, "unit_price": fee,
                      "is_recurring": False, "line_amount": fee})
    tcv = sum(line_tcv(l, term) for l in lines)
    cid, _ = make_contract_and_order(aid, landing, term, tcv, currency)
    make_opp(aid, owner, "New Business", landing, lines, True, term, currency, contract_id=cid)
    for l in lines:
        if l["is_recurring"]:
            open_seg(l["product_id"], landing, l["quantity"], cid, l["line_amount"])

    # ---- Build a chronological list of post-landing events ----
    events = []
    for ann in range(landing + 12, LAST_IDX + 1, 12):
        events.append((ann, "renewal"))
    n_expand = random.choices([0, 1, 2, 3], weights=[25, 40, 25, 10])[0]
    for _ in range(n_expand):
        em = random.randint(landing + 3, LAST_IDX)
        events.append((em, random.choices(["upsell", "cross_sell", "downgrade"],
                                           weights=[50, 35, 15])[0]))
    churn_idx = None
    if random.random() < 0.22 and landing + 13 <= LAST_IDX:
        churn_idx = random.randint(landing + 13, LAST_IDX)
    events.sort(key=lambda e: e[0])

    for (idx, kind) in events:
        if churn_idx is not None and idx >= churn_idx:
            break
        if not owned and kind != "cross_sell":
            continue
        term = random.choice(TERMS)
        if kind == "renewal":
            # Scheduled continuation — new booking, ARR unchanged.
            lines = [recurring_line(pid, owned[pid]["seats"], unit_of(owned[pid]), owned[pid]["arr"]) for pid in owned]
            if not lines:
                continue
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Renewal", idx, lines, True, term, currency, contract_id=cid)
        elif kind == "upsell":
            pid = random.choice(list(owned))
            base_seats = owned[pid]["seats"]
            base_arr = owned[pid]["arr"]
            add = random.randint(1, 8)
            unit = net_price(pid, a, idx, deal_discount(a, "Expansion", idx))
            delta_arr = round(add * unit, 2)
            lines = [recurring_line(pid, add, unit, delta_arr)]   # booking = incremental ARR
            tcv = line_tcv(lines[0], term)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Expansion", idx, lines, True, term, currency, contract_id=cid)
            close_seg(pid, idx - 1)                          # end prior (lower) segment
            open_seg(pid, idx, base_seats + add, cid, base_arr + delta_arr)  # start new (higher) segment
        elif kind == "cross_sell":
            avail = [p for p in RECURRING_PIDS if p not in owned]
            if not avail:
                continue
            pid = random.choice(avail)
            seats = seats_for(pid)
            unit = net_price(pid, a, idx, deal_discount(a, "Expansion", idx))
            lines = [recurring_line(pid, seats, unit)]
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Expansion", idx, lines, True, term, currency, contract_id=cid)
            open_seg(pid, idx, seats, cid, lines[0]["line_amount"])
        elif kind == "downgrade":
            pid = random.choice(list(owned))
            cur_seats = owned[pid]["seats"]
            if cur_seats <= 1:
                continue
            drop = random.randint(1, cur_seats - 1)
            unit, cur_arr = unit_of(owned[pid]), owned[pid]["arr"]
            delta_arr = round(-drop * unit, 2)
            lines = [{"product_id": pid, "quantity": -drop, "unit_price": unit,
                      "is_recurring": True, "line_amount": delta_arr}]
            # downgrades are processed bookings; TCV mirrors the (negative) annualized change
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, max(term, 12), abs(tcv), currency)
            make_opp(aid, owner, "Downgrade", idx, lines, True, term, currency, contract_id=cid)
            close_seg(pid, idx - 1)
            new_seats = cur_seats - drop
            open_seg(pid, idx, new_seats, cid, cur_arr + delta_arr)

    # ---- Churn ----
    if churn_idx is not None and owned:
        lost = [{"product_id": pid, "quantity": owned[pid]["seats"], "unit_price": unit_of(owned[pid]),
                 "is_recurring": True, "line_amount": owned[pid]["arr"]} for pid in list(owned)]
        make_opp(aid, owner, "Churn", churn_idx, lost, False, 12, currency, close_idx=churn_idx)
        for pid in list(owned):
            close_seg(pid, churn_idx - 1)

    # ---- Close any still-active segments at end of window ----
    for pid in list(owned):
        close_seg(pid, LAST_IDX)

# --------------------------------------------------------------------------- #
# 5) Subscriptions (one row per ARR segment) + monthly usage
# --------------------------------------------------------------------------- #
for s in segments:
    if s["arr"] <= 0 or s["end_idx"] < s["start_idx"]:
        continue
    subscriptions.append({
        "subscription_id": s["subscription_id"],
        "contract_id": s["contract_id"],
        "account_id": s["account_id"],
        "product_id": s["product_id"],
        "quantity": s["seats"],
        "annual_recurring_amount": money(s["arr"]),
        "unit_price": money(s["arr"] / s["seats"]),
        "billing_frequency": random.choice(["Annual", "Monthly", "Annual"]),
        "subscription_start_date": iso(month_start(s["start_idx"])),
        "subscription_end_date": iso(month_end(s["end_idx"])),
        "is_recurring": 1,
        "status": "Active" if s["end_idx"] >= LAST_IDX else "Inactive",
    })
    # monthly usage: consumed units correlated to entitled seats (with noise)
    base_util = random.uniform(0.45, 1.25)
    for mi in range(s["start_idx"], s["end_idx"] + 1):
        util = max(0.0, base_util + random.uniform(-0.18, 0.18))
        consumed = round(s["seats"] * util, 2)
        usage_rows.append({
            "usage_month": iso(month_start(mi)),
            "account_id": s["account_id"],
            "product_id": s["product_id"],
            "consumed_units": consumed,
            "consumed_value": money(consumed * s["arr"] / s["seats"] / 12.0),
        })

# --------------------------------------------------------------------------- #
# 6) Open pipeline opportunities (no contract / no ARR yet)
# --------------------------------------------------------------------------- #
PIPELINE_IDX = 42  # pipeline closes in H2 2026, so it is quoted at 2026 list prices
pipeline_accounts = random.sample(accounts, 55)
for a in pipeline_accounts:
    for _ in range(random.randint(1, 2)):
        term = random.choice(TERMS)
        pid = random.choice(RECURRING_PIDS)
        seats = seats_for(pid)
        d = deal_discount(a, "Pipeline", None)
        lines = [recurring_line(pid, seats, net_price(pid, a, PIPELINE_IDX, d))]
        if random.random() < 0.3:
            otp = random.choice(ONETIME_PIDS)
            fee = net_price(otp, a, PIPELINE_IDX, min(d, SERVICES_MAX_DISCOUNT))
            lines.append({"product_id": otp, "quantity": 1, "unit_price": fee,
                          "is_recurring": False, "line_amount": fee})
        otype = random.choices(["New Business", "Expansion"], weights=[40, 60])[0]
        make_opp(a["account_id"], a["owner_id"], otype, None, lines, False, term,
                 a["account_currency"], is_pipeline=True)

# --------------------------------------------------------------------------- #
# 7) Inject Salesforce <-> NetSuite reconciliation discrepancies
# --------------------------------------------------------------------------- #
all_contract_ids = [c["contract_id"] for c in contracts]
random.shuffle(all_contract_ids)
expected = {}
cursor = 0


def take(n):
    global cursor
    chunk = all_contract_ids[cursor:cursor + n]
    cursor += n
    return chunk

# (a) missing in NetSuite — drop the order entirely
missing = take(8)
for cid in missing:
    order_by_contract.pop(cid, None)
expected["missing_in_netsuite"] = len(missing)

# (b) amount mismatch — material (> $50 AND > 1%)
amount_mismatch = take(15)
for cid in amount_mismatch:
    o = order_by_contract.get(cid)
    if o:
        factor = random.choice([0.92, 0.94, 1.05, 1.07])
        o["order_total"] = money(o["order_total"] * factor)
expected["amount_mismatch"] = sum(1 for cid in amount_mismatch if cid in order_by_contract)

# (c) timing difference — order booked well after the contract start
timing = take(10)
for cid in timing:
    o = order_by_contract.get(cid)
    if o:
        start = month_start(o["_start_idx"])
        o["order_date"] = iso(start + datetime.timedelta(days=random.randint(15, 50)))
expected["timing_difference"] = sum(1 for cid in timing if cid in order_by_contract)

# (d) currency rounding — immaterial sub-$50 variance
rounding = take(6)
for cid in rounding:
    o = order_by_contract.get(cid)
    if o:
        o["order_total"] = money(o["order_total"] + random.choice([-1, 1]) * random.uniform(3, 40))
expected["currency_rounding"] = sum(1 for cid in rounding if cid in order_by_contract)

# (e) partial billing handled later (invoices < order_total)
partial = set(take(12))
expected["partially_invoiced"] = len(partial)

# Materialize the (mutated) orders + their lines + invoices
for cid, o in order_by_contract.items():
    start_idx = o.pop("_start_idx")
    ns_orders.append(o)
    # one order line per opportunity line of the originating contract's opp
    opp = next((op for op in opps if op["contract_id"] == cid), None)
    olines = [ol for ol in opp_lines if opp and ol["opportunity_id"] == opp["opportunity_id"]]
    line_sum = sum(abs(ol["line_amount"]) for ol in olines) or 1
    for ol in olines:
        share = abs(ol["line_amount"]) / line_sum
        ns_order_lines.append({
            "sales_order_line_id": nid("NSOL", 6),
            "sales_order_id": o["sales_order_id"],
            "ns_item_id": ns_item_of[ol["product_id"]],
            "quantity": abs(ol["quantity"]),
            "rate": money(ol["unit_price"]),
            "line_amount": money(o["order_total"] * share),
        })
    # invoices: full coverage unless flagged partial
    coverage = random.uniform(0.55, 0.85) if cid in partial else 1.0
    inv_total = money(o["order_total"] * coverage)
    inv_id = nid("INV", 5)
    ns_invoices.append({
        "invoice_id": inv_id,
        "ns_customer_id": o["ns_customer_id"],
        "sales_order_id": o["sales_order_id"],
        "invoice_number": inv_id.replace("INV", "I"),
        "invoice_date": iso(datetime.date.fromisoformat(o["order_date"]) + datetime.timedelta(days=random.randint(1, 20))),
        "invoice_total": inv_total,
        "invoice_status": "Paid" if random.random() < 0.85 else "Open",
        "currency_code": o["currency_code"],
    })
    for ol in ns_order_lines:
        if ol["sales_order_id"] == o["sales_order_id"]:
            ns_invoice_lines.append({
                "invoice_line_id": nid("INVL", 6),
                "invoice_id": inv_id,
                "ns_item_id": ol["ns_item_id"],
                "quantity": ol["quantity"],
                "rate": ol["rate"],
                "line_amount": money(ol["line_amount"] * coverage),
            })

# (f) orphan orders in NetSuite — no matching Salesforce contract
orphan_n = 5
for _ in range(orphan_n):
    a = random.choice(accounts)
    oid = nid("NSO", 5)
    total = money(random.uniform(15000, 120000))
    di = random.randint(0, LAST_IDX)
    ns_orders.append({
        "sales_order_id": oid,
        "ns_customer_id": ns_customer_of[a["account_id"]],
        "order_number": oid.replace("NSO", "SO"),
        "external_order_ref": nid("ORPHREF", 4),
        "order_date": iso(month_start(di) + datetime.timedelta(days=random.randint(0, 20))),
        "order_status": "Billed",
        "order_total": total,
        "currency_code": a["account_currency"],
    })
    pid = random.choice(RECURRING_PIDS)
    ns_order_lines.append({
        "sales_order_line_id": nid("NSOL", 6),
        "sales_order_id": oid, "ns_item_id": ns_item_of[pid],
        "quantity": 1, "rate": total, "line_amount": total,
    })
expected["orphan_in_netsuite"] = orphan_n

# --------------------------------------------------------------------------- #
# 8) CPQ: lost deals, price books, quotes, quote lines, approvals
#    Everything below runs after the simulation, so nothing above changes.
# --------------------------------------------------------------------------- #
landed = {}
for o in opps:
    if o["is_won"] and o["opportunity_type"] == "New Business":
        d0 = datetime.date.fromisoformat(o["close_date"])
        landed[o["account_id"]] = (d0.year - BASE_YEAR) * 12 + d0.month - BASE_MONTH
for _ in range(N_LOST):
    a = price_rng.choice(accounts)
    li = price_rng.randint(2, LAST_IDX)
    # before the account lands, a lost deal is new business; after, an expansion
    otype = "Expansion" if li > landed.get(a["account_id"], LAST_IDX + 1) else "New Business"
    d = deal_discount(a, otype, li)
    lines = [recurring_line(pid, price_rng.randint(1, 12), net_price(pid, a, li, d))
             for pid in price_rng.sample(RECURRING_PIDS, price_rng.choice([1, 1, 2]))]
    make_opp(a["account_id"], a["owner_id"], otype, li, lines, False, price_rng.choice(TERMS),
             a["account_currency"], close_idx=li)

price_books, price_book_entries = [], []
for region in REGION_LIST:
    pb_id = f"PB-{region}"
    price_books.append({"price_book_id": pb_id, "price_book_name": f"{region} Standard",
                        "region": region, "currency_code": "USD", "is_active": 1})
    for year in range(2023, 2027):
        for pid in PRICE:
            price_book_entries.append({"price_book_entry_id": nid("PBE", 5), "price_book_id": pb_id,
                                       "product_id": pid, "effective_year": year,
                                       "list_unit_price": list_price(pid, region, year)})

APPROVERS = {("Sales VP", r): fake.name() for r in REGION_LIST}
APPROVERS[("CFO", None)] = fake.name()
lines_by_opp = defaultdict(list)
for ol in opp_lines:
    lines_by_opp[ol["opportunity_id"]].append(ol)

quotes, quote_lines, approvals = [], [], []
needs_approval = []   # (quote, level, close_date) for won new pricing over the threshold
for o in opps:
    if o["opportunity_type"] == "Churn":
        continue  # a churned customer is not quoted
    acct = acct_by_id[o["account_id"]]
    region, year = acct["geo_region"], int(o["close_date"][:4])
    created = datetime.date.fromisoformat(o["created_date"])
    close = datetime.date.fromisoformat(o["close_date"])
    primary_day = max(created, close - datetime.timedelta(days=price_rng.randint(3, 15)))
    olines = lines_by_opp[o["opportunity_id"]]
    n_drafts = price_rng.choice([0, 0, 1, 1, 2])
    contact = fake.name()
    status = ("Accepted" if o["is_won"] else "Rejected") if o["is_closed"] else "Presented"
    for k in range(n_drafts + 1):
        is_primary = k == n_drafts
        step = 0.03 * (n_drafts - k)   # earlier drafts conceded less
        qd = primary_day if is_primary else created + (primary_day - created) * (k + 1) // (n_drafts + 1)
        q = {"quote_id": nid("QTE", 6), "opportunity_id": o["opportunity_id"], "account_id": o["account_id"],
             "owner_id": o["owner_id"], "price_book_id": f"PB-{region}",
             "quote_status": status if is_primary else "Superseded", "is_primary": int(is_primary),
             "created_date": iso(qd), "expiration_date": iso(qd + datetime.timedelta(days=30)),
             "contact_name": contact, "contact_email": fake.safe_email()}
        quotes.append(q)
        q_list = q_net = 0.0
        for ol in olines:
            lp = list_price(ol["product_id"], region, year)
            line_disc = max(0.0, 1 - ol["unit_price"] / lp)
            unit = ol["unit_price"] if is_primary else round(lp * (1 - max(0.0, line_disc - step)), 2)
            net_total = ol["line_amount"] if is_primary else round(unit * ol["quantity"], 2)
            quote_lines.append({"quote_line_id": nid("QL", 6), "quote_id": q["quote_id"],
                                "product_id": ol["product_id"], "quantity": ol["quantity"],
                                "list_unit_price": lp, "discount_pct": round(1 - unit / lp, 4),
                                "net_unit_price": unit, "net_total": net_total,
                                "is_recurring": ol["is_recurring"], "term_months": ol["term_months"]})
            if ol["quantity"] > 0:
                q_list += lp * ol["quantity"]
                q_net += net_total
        qdisc = 1 - q_net / q_list if q_list else 0
        if (is_primary and status == "Accepted" and o["opportunity_type"] in ("New Business", "Expansion")
                and qdisc > APPROVAL_THRESHOLD):
            needs_approval.append((q, "CFO" if qdisc > CFO_THRESHOLD else "Sales VP", close, region))

unapproved = set(price_rng.sample(range(len(needs_approval)), UNAPPROVED_SEEDED))
for i, (q, level, close, region) in enumerate(needs_approval):
    if i in unapproved:
        continue
    asked = datetime.date.fromisoformat(q["created_date"])
    wait = price_rng.randint(1, 4) if level == "Sales VP" else price_rng.randint(3, 9)
    approvals.append({"approval_id": nid("APR", 5), "quote_id": q["quote_id"], "approval_level": level,
                      "approver_name": APPROVERS[(level, region if level == "Sales VP" else None)],
                      "approval_status": "Approved", "requested_date": iso(asked),
                      "decided_date": iso(min(close, asked + datetime.timedelta(days=wait)))})

cpq_findings = {"unapproved_discounts": UNAPPROVED_SEEDED, "approval_threshold": APPROVAL_THRESHOLD,
                "quarter_end_extra_discount": QUARTER_END_EXTRA, "heavy_discounters": HEAVY_DISCOUNTERS}

# --------------------------------------------------------------------------- #
# Write CSVs
# --------------------------------------------------------------------------- #
def write(df_rows, path, cols=None):
    df = pd.DataFrame(df_rows)
    if cols:
        df = df[cols]
    df.to_csv(path, index=False)
    return len(df)


tables = {
    os.path.join(SF_DIR, "salesforce_accounts.csv"): accounts,
    os.path.join(SF_DIR, "salesforce_users.csv"): users,
    os.path.join(SF_DIR, "salesforce_products.csv"): products,
    os.path.join(SF_DIR, "salesforce_opportunities.csv"): opps,
    os.path.join(SF_DIR, "salesforce_opportunity_line_items.csv"): opp_lines,
    os.path.join(SF_DIR, "salesforce_contracts.csv"): contracts,
    os.path.join(SF_DIR, "salesforce_subscriptions.csv"): subscriptions,
    os.path.join(NS_DIR, "netsuite_customers.csv"): ns_customers,
    os.path.join(NS_DIR, "netsuite_items.csv"): ns_items,
    os.path.join(NS_DIR, "netsuite_sales_orders.csv"): ns_orders,
    os.path.join(NS_DIR, "netsuite_sales_order_lines.csv"): ns_order_lines,
    os.path.join(NS_DIR, "netsuite_invoices.csv"): ns_invoices,
    os.path.join(NS_DIR, "netsuite_invoice_lines.csv"): ns_invoice_lines,
    os.path.join(USE_DIR, "usage_monthly.csv"): usage_rows,
    os.path.join(SF_DIR, "salesforce_price_books.csv"): price_books,
    os.path.join(SF_DIR, "salesforce_price_book_entries.csv"): price_book_entries,
    os.path.join(SF_DIR, "salesforce_quotes.csv"): quotes,
    os.path.join(SF_DIR, "salesforce_quote_lines.csv"): quote_lines,
    os.path.join(SF_DIR, "salesforce_quote_approvals.csv"): approvals,
}

print("Synthetic seed generation (seed=%d)" % SEED)
print("-" * 60)
for path, rows in tables.items():
    n = write(rows, path)
    print(f"  {os.path.relpath(path, ROOT):<48} {n:>7,} rows")

with open(os.path.join(HERE, "seeded_discrepancy_counts.json"), "w") as f:
    json.dump(expected, f, indent=2)
with open(os.path.join(HERE, "seeded_cpq_findings.json"), "w") as f:
    json.dump(cpq_findings, f, indent=2)

print("-" * 60)
print("Seeded reconciliation discrepancies (for dbt tests):")
for k, v in expected.items():
    print(f"  {k:<22} {v}")
print("Seeded CPQ findings:", cpq_findings)
print("Done.")
