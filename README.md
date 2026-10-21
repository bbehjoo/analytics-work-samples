# Data Leadership Work Samples · Behrang Behjoo

[![build](https://github.com/bbehjoo/analytics-work-samples/actions/workflows/ci.yml/badge.svg)](https://github.com/bbehjoo/analytics-work-samples/actions/workflows/ci.yml)

**One B2B SaaS company's data, end to end:** the revenue numbers, the people data,
and the rules for who gets to see what. Modeled, tested, governed and explained in
one repo. Everything here is synthetic or my own published work; nothing proprietary.

**[See it live →](https://bbehjoo.github.io/analytics-work-samples/)**
&nbsp;·&nbsp; [Revenue report](https://bbehjoo.github.io/analytics-work-samples/revenue.html)
&nbsp;·&nbsp; [People report](https://bbehjoo.github.io/analytics-work-samples/people.html)
&nbsp;·&nbsp; [Who sees what](https://bbehjoo.github.io/analytics-work-samples/access.html)

---

## How I run data, with receipts

| Principle | What it means here | Proof in the code |
|---|---|---|
| **One number, one definition** | ARR, NRR and ~20 metrics are defined once in a semantic layer, so every dashboard and every AI agent gets the same answer. | [`metrics.yml`](saas-data-platform/models/semantic/metrics.yml) |
| **The numbers reconcile** | The ARR waterfall balances to the cent, and every CRM contract is matched to its ERP order. | [`assert_arr_waterfall_integrity.sql`](saas-data-platform/tests/assert_arr_waterfall_integrity.sql) |
| **Private by default** | Every column about a person is classified. One policy file decides what HR, Finance, a sales manager, an analyst and an AI agent each see. Pay, health and gender never reach analysts or AI, and tests prove it. | [`access_policy.csv`](saas-data-platform/seeds/governance/access_policy.csv) · [GOVERNANCE.md](saas-data-platform/GOVERNANCE.md) |
| **Every table has an owner** | Every model belongs to a named team. Certified tables have enforced contracts. CI fails if ownership or classification slips. | [`groups.yml`](saas-data-platform/models/groups.yml) · [`check_governance.py`](saas-data-platform/scripts/check_governance.py) |
| **Every chart ends in a decision** | Each finding says what it is, why it matters and what to do next. | [Revenue](saas-data-platform/reports/revenue_insights_report.md) · [People](saas-data-platform/reports/people_insights_report.md) |

---

## 1. [`saas-data-platform/`](saas-data-platform/): the whole stack in one dbt project

- **Revenue.** Salesforce (CRM) + NetSuite (ERP) + product usage, modeled into a star
  schema: ARR waterfall, bookings and pipeline, retention, and a CRM-to-ERP
  reconciliation that surfaces real finance discrepancies. MetricFlow semantic layer
  on top.
- **People.** An HRIS (names, pay, leave, gender) modeled into headcount, attrition,
  pay equity and ARR per employee, the metric that joins the two domains.
- **Governance.** Four sensitivity classes. Role-scoped views generated from one
  policy file. Groups under 5 suppressed. Raw HR data that other teams' models can't
  even reference. The same rules mapped to BigQuery grants, row access policies and
  policy tags for production.
- **Quality.** 132 data tests, 8 of them "proof" tests (the waterfall balances, the
  reconciliation is complete, nothing leaks), enforced contracts, and CI on every push.

It runs locally on DuckDB with generated data: `dbt build` → `PASS=197`.

**What the data says** (each with what to do, in the reports):

- ARR grew to **$82.1M**. Expansion now drives growth, but churn tripled to **$8.3M** in 2025.
- **$2.2M of signed contracts never reached the ERP**, a close-the-books risk.
- ARR per employee peaked at **$220k**, then slipped to $199k as hiring outpaced revenue.
- Women and men are paid the same on average. **At L4, women are paid 6.4% less**
  against the same pay band. Closing it costs about $345k a year.

→ [How the platform is built](saas-data-platform/README.md) ·
[Who sees what, and how it's proven](saas-data-platform/GOVERNANCE.md) ·
[ERD & lineage](saas-data-platform/DATA_MODEL.md)

## 2. [`fight-algorithm-samples/`](fight-algorithm-samples/): beyond SQL

Curated, unmodified files from [**thefightalgorithm.com**](https://thefightalgorithm.com),
an independent MMA analytics publication I build and run end to end: a Python + DuckDB
pipeline over ~8,500 UFC fights powering an interactive Next.js site.

**What it shows**: a scikit-learn **stacking ensemble** with calibration and
cross-validation, **complex analytical SQL** (window functions, self-joins), and a
typed **Monte Carlo simulation engine** in TypeScript. Statistics, ML and
procedural code beyond SQL, plus a product I own from pipeline to published page.

→ See [fight-algorithm-samples/README.md](fight-algorithm-samples/README.md).

---

## Repo map

```
.
├── saas-data-platform/        the dbt project: revenue + people + governance
│   ├── models/                staging → intermediate → marts · people · secure views
│   ├── seeds/governance/      access_policy.csv, roles.csv   ← who sees what
│   ├── macros/governance/     secure_view(): turns the policy into SQL
│   ├── tests/                 proof tests: reconciliation and governance
│   ├── governance/bigquery/   production reference: grants, row policies, policy tags
│   ├── scripts/               data generators, governance check, site builder
│   └── reports/               revenue and people insight reports
├── docs/                      the published site (GitHub Pages)
├── fight-algorithm-samples/   ML, analytical SQL, Monte Carlo simulation
└── .github/workflows/         CI: dbt build + governance check on every push
```

## Run it

```bash
cd saas-data-platform
pip install -r requirements.txt
dbt deps && dbt build                  # every model and every test
python scripts/check_governance.py     # owners, classification, proof tests
```

### A note on the data

Everything in the dbt project is **synthetic**, generated deterministically by
[`generate_seeds.py`](saas-data-platform/scripts/generate_seeds.py) (Salesforce,
NetSuite, usage) and
[`generate_people_seeds.py`](saas-data-platform/scripts/generate_people_seeds.py)
(HRIS). The people are invented; names, emails and pay come from a fixed random seed.
Findings like the reconciliation discrepancies and the L4 pay gap are seeded on
purpose, so the models have something real to find. The Fight Algorithm files are my
own published work.
