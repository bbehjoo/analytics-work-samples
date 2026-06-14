#!/usr/bin/env python
"""
generate_seeds.py — Deterministic synthetic data generator for the
Revenue Analytics dbt project (Salesforce CRM + NetSuite ERP).

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
    ("GC-METRICS",  "Observability",        "Metrics",     "Grafana Cloud Metrics",     True,  18000),
    ("PROM-MGD",    "Observability",        "Metrics",     "Prometheus Managed",        True,  15000),
    ("GC-LOGS",     "Observability",        "Logs",        "Grafana Cloud Logs",        True,  22000),
    ("LOKI-ENT",    "Observability",        "Logs",        "Loki Enterprise",           True,  30000),
    ("GC-TRACES",   "Observability",        "Traces",      "Grafana Cloud Traces",      True,  16000),
    ("TEMPO-ENT",   "Observability",        "Traces",      "Tempo Enterprise",          True,  28000),
    ("ONCALL",      "Incident Response",    "On-Call",     "Grafana OnCall",            True,  12000),
    ("SLO",         "Incident Response",    "SLO",         "Grafana SLO",               True,  14000),
    ("ENT-STACK",   "Observability",        "Platform",    "Grafana Enterprise Stack",  True,  95000),
    ("PS-IMPL",     "Professional Services","Onboarding",  "Implementation Services",   False, 25000),
    ("PS-TRAIN",    "Professional Services","Training",    "Training Package",          False, 8000),
    ("PS-MIGR",     "Professional Services","Migration",   "Migration Services",        False, 18000),
]
RECURRING_PIDS = [p[0] for p in PRODUCTS if p[4]]
ONETIME_PIDS = [p[0] for p in PRODUCTS if not p[4]]
PRICE = {p[0]: p[5] for p in PRODUCTS}

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
        "list_unit_price": price,
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
        "subsidiary": {"NA": "Grafana Labs Inc", "EMEA": "Grafana Labs EMEA",
                       "APAC": "Grafana Labs APAC", "LATAM": "Grafana Labs Inc"}[a["geo_region"]],
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


def recurring_line(pid, seats, line_amount=None):
    amt = seats * PRICE[pid] if line_amount is None else line_amount
    return {"product_id": pid, "quantity": seats, "unit_price": PRICE[pid],
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

    def open_seg(pid, idx, seats, contract_id):
        owned[pid] = {"seats": seats, "arr": seats * PRICE[pid], "start_idx": idx,
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
    lines = [recurring_line(pid, seats_for(pid)) for pid in init_pids]
    if random.random() < 0.5:  # ~half of landings attach a one-time services line
        otp = random.choice(ONETIME_PIDS)
        lines.append({"product_id": otp, "quantity": 1, "unit_price": PRICE[otp],
                      "is_recurring": False, "line_amount": PRICE[otp]})
    tcv = sum(line_tcv(l, term) for l in lines)
    cid, _ = make_contract_and_order(aid, landing, term, tcv, currency)
    make_opp(aid, owner, "New Business", landing, lines, True, term, currency, contract_id=cid)
    for l in lines:
        if l["is_recurring"]:
            open_seg(l["product_id"], landing, l["quantity"], cid)

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
            lines = [recurring_line(pid, owned[pid]["seats"], owned[pid]["arr"]) for pid in owned]
            if not lines:
                continue
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Renewal", idx, lines, True, term, currency, contract_id=cid)
        elif kind == "upsell":
            pid = random.choice(list(owned))
            base_seats = owned[pid]["seats"]
            add = random.randint(1, 8)
            delta_arr = add * PRICE[pid]
            lines = [recurring_line(pid, add, delta_arr)]   # booking = incremental ARR
            tcv = line_tcv(lines[0], term)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Expansion", idx, lines, True, term, currency, contract_id=cid)
            close_seg(pid, idx - 1)                          # end prior (lower) segment
            open_seg(pid, idx, base_seats + add, cid)        # start new (higher) segment
        elif kind == "cross_sell":
            avail = [p for p in RECURRING_PIDS if p not in owned]
            if not avail:
                continue
            pid = random.choice(avail)
            seats = seats_for(pid)
            lines = [recurring_line(pid, seats)]
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, term, tcv, currency)
            make_opp(aid, owner, "Expansion", idx, lines, True, term, currency, contract_id=cid)
            open_seg(pid, idx, seats, cid)
        elif kind == "downgrade":
            pid = random.choice(list(owned))
            cur_seats = owned[pid]["seats"]
            if cur_seats <= 1:
                continue
            drop = random.randint(1, cur_seats - 1)
            delta_arr = -drop * PRICE[pid]
            lines = [{"product_id": pid, "quantity": -drop, "unit_price": PRICE[pid],
                      "is_recurring": True, "line_amount": delta_arr}]
            # downgrades are processed bookings; TCV mirrors the (negative) annualized change
            tcv = sum(line_tcv(l, term) for l in lines)
            cid, _ = make_contract_and_order(aid, idx, max(term, 12), abs(tcv), currency)
            make_opp(aid, owner, "Downgrade", idx, lines, True, term, currency, contract_id=cid)
            close_seg(pid, idx - 1)
            new_seats = cur_seats - drop
            open_seg(pid, idx, new_seats, cid)

    # ---- Churn ----
    if churn_idx is not None and owned:
        lost = [{"product_id": pid, "quantity": owned[pid]["seats"], "unit_price": PRICE[pid],
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
        "unit_price": money(PRICE[s["product_id"]]),
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
            "consumed_value": money(consumed * PRICE[s["product_id"]] / 12.0),
        })

# --------------------------------------------------------------------------- #
# 6) Open pipeline opportunities (no contract / no ARR yet)
# --------------------------------------------------------------------------- #
pipeline_accounts = random.sample(accounts, 55)
for a in pipeline_accounts:
    for _ in range(random.randint(1, 2)):
        term = random.choice(TERMS)
        pid = random.choice(RECURRING_PIDS)
        seats = seats_for(pid)
        lines = [recurring_line(pid, seats)]
        if random.random() < 0.3:
            otp = random.choice(ONETIME_PIDS)
            lines.append({"product_id": otp, "quantity": 1, "unit_price": PRICE[otp],
                          "is_recurring": False, "line_amount": PRICE[otp]})
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
}

print("Synthetic seed generation (seed=%d)" % SEED)
print("-" * 60)
for path, rows in tables.items():
    n = write(rows, path)
    print(f"  {os.path.relpath(path, ROOT):<48} {n:>7,} rows")

with open(os.path.join(HERE, "seeded_discrepancy_counts.json"), "w") as f:
    json.dump(expected, f, indent=2)

print("-" * 60)
print("Seeded reconciliation discrepancies (for dbt tests):")
for k, v in expected.items():
    print(f"  {k:<22} {v}")
print("Done.")
