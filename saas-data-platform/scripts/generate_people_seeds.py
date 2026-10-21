#!/usr/bin/env python
"""
generate_people_seeds.py — Deterministic synthetic HRIS data for the people
domain of the SaaS data platform.

This is the sensitive half of the company: names, emails, birth dates, pay,
leave (health information) and gender. Everything is synthetic (Faker + a fixed
seed) and safe to publish. It uses its OWN random generators, so the revenue
seeds from generate_seeds.py are untouched.

What it models
--------------
An HRIS (Workday-shaped) export, landed as four tables:

  * hris_workers        one row per person ever employed (identity, org, dates)
  * hris_compensation   current pay per worker (base, bonus target, equity)
  * hris_comp_bands     pay bands by level x region
  * hris_leave          leaves of absence (medical = health information)

Headcount grows with ARR: about 95 people in January 2023 to 412 at the end of
2025. The 25 Salesforce sales reps are employees here too
(salesforce_user_id), so the revenue and people domains join.

Seeded findings, so the people reports have something real to surface:
  * a pay gap at one level (women at L4 paid ~6% below men, against the same band)
  * an attrition hotspot (Customer Success loses people about twice as fast)
They are written to scripts/seeded_people_findings.json.

Run:  python scripts/generate_people_seeds.py   (after generate_seeds.py)
"""
import os
import json
import random
import datetime
import unicodedata

import pandas as pd
from faker import Faker
from faker.providers.person.en_US import Provider as EnUsPersonProvider

# --------------------------------------------------------------------------- #
# Reproducibility: separate generators from the revenue seeds
# --------------------------------------------------------------------------- #
SEED = 7
rng = random.Random(SEED)
Faker.seed(SEED)
LOCALES = ["en_US", "en_CA", "en_GB", "de_DE", "fr_FR", "nl_NL", "sv_SE",
           "en_AU", "ja_JP", "en_IN", "pt_BR", "es_MX"]
fake = Faker(LOCALES)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SF_USERS = os.path.join(ROOT, "seeds", "salesforce", "salesforce_users.csv")
OUT_DIR = os.path.join(ROOT, "seeds", "hris")
os.makedirs(OUT_DIR, exist_ok=True)

AS_OF = datetime.date(2025, 12, 31)
BASE_YEAR = 2023
N_MONTHS = 36  # Jan 2023 .. Dec 2025


def month_start(i: int) -> datetime.date:
    return datetime.date(BASE_YEAR + i // 12, i % 12 + 1, 1)


def month_end(i: int) -> datetime.date:
    s = month_start(i + 1)
    return s - datetime.timedelta(days=1)


def day_in_month(i: int) -> datetime.date:
    return month_start(i) + datetime.timedelta(days=rng.randint(0, 27))


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
REGIONS = {
    "NA": ["United States", "Canada"],
    "EMEA": ["United Kingdom", "Germany", "France", "Netherlands", "Sweden"],
    "APAC": ["Australia", "Japan", "Singapore", "India"],
    "LATAM": ["Brazil", "Mexico"],
}
REGION_WEIGHTS = {"NA": 52, "EMEA": 27, "APAC": 13, "LATAM": 8}
COUNTRY_LOCALE = {
    "United States": "en_US", "Canada": "en_CA", "United Kingdom": "en_GB",
    "Germany": "de_DE", "France": "fr_FR", "Netherlands": "nl_NL", "Sweden": "sv_SE",
    "Australia": "en_AU", "Japan": "ja_JP", "Singapore": "en_US", "India": "en_IN",
    "Brazil": "pt_BR", "Mexico": "es_MX",
}

# department -> (hiring weight, role noun, monthly voluntary exit probability)
DEPARTMENTS = {
    "Engineering":      (30, "Software Engineer",        0.0075),
    "Sales":            (22, "Account Executive",        0.0090),
    "Customer Success": (16, "Customer Success Manager", 0.0200),  # seeded hotspot
    "Marketing":        (10, "Marketing Specialist",     0.0080),
    "Product":          (8,  "Product Manager",          0.0065),
    "Finance":          (6,  "Financial Analyst",        0.0060),
    "People":           (5,  "People Partner",           0.0070),
    "Legal":            (0,  "Counsel",                  0.0),     # 3 people, never hired again
}
INVOLUNTARY_P = 0.0028

LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
LEVEL_WEIGHTS = [6, 18, 27, 24, 14, 8, 3]
LEVEL_AGE = {"L1": 24, "L2": 27, "L3": 30, "L4": 34, "L5": 38, "L6": 41, "L7": 46}
BAND_MID_NA = {"L1": 70000, "L2": 90000, "L3": 115000, "L4": 140000,
               "L5": 170000, "L6": 200000, "L7": 245000}
REGION_PAY = {"NA": 1.00, "EMEA": 0.85, "APAC": 0.75, "LATAM": 0.55}
EQUITY = {"L1": 5000, "L2": 10000, "L3": 20000, "L4": 35000,
          "L5": 60000, "L6": 90000, "L7": 150000}

GENDERS = ["Woman", "Man", "Non-binary"]
GENDER_WEIGHTS = [45, 52, 3]

PAY_GAP_LEVEL, PAY_GAP_FACTOR = "L4", 0.94   # seeded finding

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_used_emails = set()


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def person_name(country: str, gender: str):
    loc = COUNTRY_LOCALE[country]
    f = fake[loc]
    if loc == "ja_JP":
        first = {"Woman": f.first_romanized_name_female, "Man": f.first_romanized_name_male}.get(
            gender, f.first_romanized_name)()
        return first, f.last_romanized_name()
    first = {"Woman": f.first_name_female, "Man": f.first_name_male}.get(gender, f.first_name)()
    return first, f.last_name()


FEMALE_FIRST = set(EnUsPersonProvider.first_names_female)


def gender_for(first_name: str) -> str:
    """Reps arrive with a CRM name only; keep their recorded gender plausible."""
    if rng.random() < 0.03:
        return "Non-binary"
    return "Woman" if first_name in FEMALE_FIRST else "Man"


def work_email(first: str, last: str) -> str:
    base = ".".join(ascii_fold(p).lower().replace(" ", "").replace("'", "") for p in (first, last))
    email, n = f"{base}@saasco.com", 1
    while email in _used_emails:
        n += 1
        email = f"{base}{n}@saasco.com"
    _used_emails.add(email)
    return email


def job_title(dept: str, level: str) -> str:
    noun = DEPARTMENTS[dept][1]
    if level == "L7":
        return f"Director, {dept}"
    if level == "L6":
        return f"Manager, {dept}"
    prefix = {"L1": "Associate ", "L2": "", "L3": "", "L4": "Senior ", "L5": "Lead "}[level]
    suffix = " II" if level == "L3" else ""
    return f"{prefix}{noun}{suffix}"


def pick_region():
    return rng.choices(list(REGION_WEIGHTS), weights=list(REGION_WEIGHTS.values()))[0]


workers, comp, leaves = [], [], []


def new_worker(dept, level, region, hire_date, protected=False, sf_user=None, name=None):
    country = rng.choice(REGIONS[region])
    if name:
        first, last = name
        gender = gender_for(first)
    else:
        gender = rng.choices(GENDERS, weights=GENDER_WEIGHTS)[0]
        first, last = person_name(country, gender)
    age = max(22, min(64, round(rng.gauss(LEVEL_AGE[level], 4))))
    dob = AS_OF - datetime.timedelta(days=age * 365 + rng.randint(0, 364))
    w = {
        "worker_id": None,  # assigned after sorting by hire date
        "full_name": f"{first} {last}",
        "work_email": work_email(first, last),
        "personal_email": fake["en_US"].safe_email(),
        "date_of_birth": dob,
        "home_postal_code": fake[COUNTRY_LOCALE[country]].postcode(),
        "gender": gender,
        "department": dept,
        "job_title": job_title(dept, level),
        "job_level": level,
        "region": region,
        "country": country,
        "manager_id": None,
        "hire_date": hire_date,
        "termination_date": None,
        "termination_type": None,
        "salesforce_user_id": sf_user,
        "_protected": protected,
    }
    workers.append(w)
    return w


# --------------------------------------------------------------------------- #
# 1) Starting cohort (people hired before 2023)
# --------------------------------------------------------------------------- #
def early_hire():
    start = datetime.date(2018, 3, 1)
    return start + datetime.timedelta(days=rng.randint(0, (datetime.date(2022, 12, 20) - start).days))


# the 25 Salesforce reps are Account Executives in Sales, in their CRM region
sf_users = pd.read_csv(SF_USERS, keep_default_na=False)  # "NA" is a region, not a null
for u in sf_users.itertuples():
    first, last = u.user_name.split(" ", 1)
    hired = datetime.date(2020, 1, 6) + datetime.timedelta(days=rng.randint(0, 1050))
    new_worker("Sales", rng.choice(["L3", "L3", "L4", "L5"]), u.sales_region, hired,
               protected=True, sf_user=u.user_id, name=(first, last))

# a director per department (Legal is three counsel with no director)
for dept in DEPARTMENTS:
    if dept != "Legal":
        new_worker(dept, "L7", "NA", early_hire(), protected=True)
for lvl in ["L6", "L5", "L4"]:
    new_worker("Legal", lvl, "NA", early_hire(), protected=True)

HIRING_DEPTS = [d for d, v in DEPARTMENTS.items() if v[0] > 0]
HIRING_WEIGHTS = [DEPARTMENTS[d][0] for d in HIRING_DEPTS]


def hire_level():
    return rng.choices(LEVELS[:6], weights=LEVEL_WEIGHTS[:6])[0]


while len(workers) < 95:
    new_worker(rng.choices(HIRING_DEPTS, weights=HIRING_WEIGHTS)[0], hire_level(),
               pick_region(), early_hire())

# --------------------------------------------------------------------------- #
# 2) Monthly simulation: exits, then hiring up to a target that tracks ARR
# --------------------------------------------------------------------------- #
ANCHORS = [(-1, 95), (11, 190), (23, 285), (35, 412)]


def target(m: int) -> int:
    for (m0, h0), (m1, h1) in zip(ANCHORS, ANCHORS[1:]):
        if m0 <= m <= m1:
            return round(h0 + (h1 - h0) * (m - m0) / (m1 - m0))
    raise ValueError(m)


for m in range(N_MONTHS):
    active = [w for w in workers if w["termination_date"] is None]
    for w in active:
        if w["_protected"] or w["hire_date"] > month_start(m):
            continue
        p_vol = DEPARTMENTS[w["department"]][2]
        r = rng.random()
        if r < p_vol:
            w["termination_date"], w["termination_type"] = day_in_month(m), "Voluntary"
        elif r < p_vol + INVOLUNTARY_P:
            w["termination_date"], w["termination_type"] = day_in_month(m), "Involuntary"
    still = sum(1 for w in workers if w["termination_date"] is None)
    for _ in range(max(0, target(m) - still)):
        new_worker(rng.choices(HIRING_DEPTS, weights=HIRING_WEIGHTS)[0], hire_level(),
                   pick_region(), day_in_month(m))

# a few exits land after their own month's hires; keep dates sane
for w in workers:
    if w["termination_date"] and w["termination_date"] <= w["hire_date"]:
        w["termination_date"] = w["hire_date"] + datetime.timedelta(days=rng.randint(30, 90))
        if w["termination_date"] > AS_OF:
            w["termination_date"] = w["termination_type"] = None

# --------------------------------------------------------------------------- #
# 3) IDs (by hire date) and managers
# --------------------------------------------------------------------------- #
workers.sort(key=lambda w: (w["hire_date"], w["full_name"]))
for i, w in enumerate(workers, start=1):
    w["worker_id"] = f"EMP-{i:05d}"

for w in workers:
    if w["job_level"] == "L7":
        continue
    pool = [m for m in workers
            if m["department"] == w["department"] and m is not w
            and m["job_level"] in ("L6", "L7") and m["termination_date"] is None]
    same_region = [m for m in pool if m["region"] == w["region"] and m["job_level"] == "L6"]
    boss = rng.choice(same_region or pool) if pool else None
    if w["job_level"] == "L6" or boss is None:
        boss = next((m for m in workers if m["department"] == w["department"]
                     and m["job_level"] == "L7"), None) or boss
    w["manager_id"] = boss["worker_id"] if boss and boss is not w else None

# --------------------------------------------------------------------------- #
# 4) Pay bands and current compensation
# --------------------------------------------------------------------------- #
bands = []
for lvl in LEVELS:
    for region, factor in REGION_PAY.items():
        mid = round(BAND_MID_NA[lvl] * factor, -3)
        bands.append({"job_level": lvl, "region": region,
                      "band_min_usd": round(mid * 0.8, -3), "band_mid_usd": mid,
                      "band_max_usd": round(mid * 1.2, -3)})
band_mid = {(b["job_level"], b["region"]): b["band_mid_usd"] for b in bands}

for w in workers:
    mid = band_mid[(w["job_level"], w["region"])]
    ratio = min(1.15, max(0.85, rng.gauss(1.0, 0.045)))
    if w["job_level"] == PAY_GAP_LEVEL and w["gender"] == "Woman":
        ratio *= PAY_GAP_FACTOR
    elif w["gender"] == "Woman":
        ratio *= rng.uniform(0.99, 1.01)
    if w["department"] == "Sales":
        bonus = 0.50
    else:
        bonus = {"L1": .08, "L2": .08, "L3": .08, "L4": .12, "L5": .12, "L6": .20, "L7": .20}[w["job_level"]]
    comp.append({
        "worker_id": w["worker_id"],
        "effective_date": max(w["hire_date"], datetime.date(2025, 4, 1)) if w["termination_date"] is None
                          else w["hire_date"],
        "base_salary_usd": int(round(mid * ratio / 500.0) * 500),
        "bonus_target_pct": bonus,
        "equity_grant_usd": int(round(EQUITY[w["job_level"]] * rng.uniform(0.7, 1.4), -3)),
    })

# --------------------------------------------------------------------------- #
# 5) Leaves of absence (medical leave is health information)
# --------------------------------------------------------------------------- #
LEAVE_TYPES = {"Medical": (45, 14, 84), "Parental": (40, 56, 140), "Personal": (15, 7, 42)}


def add_leave(w, start):
    kind = rng.choices(list(LEAVE_TYPES), weights=[v[0] for v in LEAVE_TYPES.values()])[0]
    lo, hi = LEAVE_TYPES[kind][1:]
    end = start + datetime.timedelta(days=rng.randint(lo, hi))
    leaves.append({"leave_id": None, "worker_id": w["worker_id"], "leave_type": kind,
                   "start_date": start, "end_date": end})


window_start = datetime.date(2023, 1, 1)
for w in workers:
    lo = max(w["hire_date"] + datetime.timedelta(days=60), window_start)
    hi = min(w["termination_date"] or AS_OF, AS_OF) - datetime.timedelta(days=7)
    if hi > lo and rng.random() < 0.14:
        add_leave(w, lo + datetime.timedelta(days=rng.randint(0, (hi - lo).days)))
    # a few people are out on the as-of date
    if w["termination_date"] is None and w["hire_date"] < datetime.date(2025, 6, 1) and rng.random() < 0.022:
        add_leave(w, AS_OF - datetime.timedelta(days=rng.randint(5, 40)))

# Seeded case for the access demo: one EMEA sales rep is out on medical leave on
# the snapshot date, so the EMEA manager's view has an "Away" to show.
rep = next(w for w in workers
           if w["department"] == "Sales" and w["region"] == "EMEA" and w["salesforce_user_id"]
           and w["termination_date"] is None
           and not any(r["worker_id"] == w["worker_id"] for r in leaves))
leaves.append({"leave_id": None, "worker_id": rep["worker_id"], "leave_type": "Medical",
               "start_date": datetime.date(2025, 12, 8), "end_date": datetime.date(2026, 1, 30)})

leaves.sort(key=lambda r: (r["start_date"], r["worker_id"]))
for i, r in enumerate(leaves, start=1):
    r["leave_id"] = f"LOA-{i:05d}"

# --------------------------------------------------------------------------- #
# Write CSVs
# --------------------------------------------------------------------------- #
WORKER_COLS = ["worker_id", "full_name", "work_email", "personal_email", "date_of_birth",
               "home_postal_code", "gender", "department", "job_title", "job_level", "region",
               "country", "manager_id", "hire_date", "termination_date", "termination_type",
               "salesforce_user_id"]

tables = {
    "hris_workers.csv": pd.DataFrame(workers)[WORKER_COLS],
    "hris_compensation.csv": pd.DataFrame(comp),
    "hris_comp_bands.csv": pd.DataFrame(bands),
    "hris_leave.csv": pd.DataFrame(leaves),
}
print("Synthetic HRIS seed generation (seed=%d)" % SEED)
print("-" * 60)
for name, df in tables.items():
    df.to_csv(os.path.join(OUT_DIR, name), index=False)
    print(f"  seeds/hris/{name:<38} {len(df):>7,} rows")

active = [w for w in workers if w["termination_date"] is None]
findings = {
    "headcount_as_of": len(active),
    "pay_gap_level": PAY_GAP_LEVEL,
    "pay_gap_pct": round((PAY_GAP_FACTOR - 1) * 100),
    "attrition_hotspot": "Customer Success",
}
with open(os.path.join(HERE, "seeded_people_findings.json"), "w") as f:
    json.dump(findings, f, indent=2)
print("-" * 60)
print(f"Active headcount on {AS_OF}: {len(active)}  (ever employed: {len(workers)})")
print("Seeded findings:", findings)
