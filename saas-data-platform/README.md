# SaaS Data Platform: dbt project

One B2B SaaS company's data platform, end to end, in one dbt project:

- **Revenue.** **Salesforce** (CRM), **NetSuite** (ERP) and product usage, modeled into
  a star schema of revenue marts with a **MetricFlow semantic layer**: ARR waterfall,
  bookings, retention, and a CRM-to-ERP reconciliation.
- **People.** An **HRIS** (names, pay, leave, gender), modeled into a restricted
  people domain with role-scoped secure views and suppressed aggregates.
- **Governance.** Every column that describes a person is classified, one policy
  file decides who sees what, and tests prove nothing leaks. See
  **[GOVERNANCE.md](GOVERNANCE.md)**.

It runs locally on **DuckDB** with **synthetic** data (no warehouse, no credentials,
nothing proprietary). The SQL is kept BigQuery-portable, and
[`governance/bigquery/`](governance/bigquery/) shows how the access rules deploy there.

It mirrors the revenue marts I've built in B2B SaaS, rebuilt from scratch on
generated data, plus the people data and access controls a data leader is
accountable for.

📊 **[Live site](https://bbehjoo.github.io/analytics-work-samples/)** &nbsp;·&nbsp; 🧭 **[Interactive lineage map](https://bbehjoo.github.io/analytics-work-samples/architecture.html)** &nbsp;·&nbsp; 🔐 **[Governance](GOVERNANCE.md)** &nbsp;·&nbsp; 🗺️ **[ERD & lineage](DATA_MODEL.md)**

---

## Quickstart

```bash
# from this directory (saas-data-platform/)
python -m venv .venv && source .venv/Scripts/activate   # Windows; use bin/activate on macOS/Linux
pip install -r requirements.txt

python scripts/generate_seeds.py          # synthetic Salesforce + NetSuite + usage data
python scripts/generate_people_seeds.py   # synthetic HRIS data (its own random seed)

dbt deps                                  # install dbt_utils
dbt build                                 # seeds -> models -> secure views + every test
python scripts/check_governance.py        # owners, classification, proof tests
python scripts/build_site.py              # regenerate the published pages in ../docs/
```

`dbt build` runs the whole pipeline and every test in one command (expect
`PASS=197`). A `warehouse.duckdb` file is created in this folder and is git-ignored.
CI runs the same steps on every push ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

---

## Architecture

```
REVENUE (owner: Revenue Analytics)                 PEOPLE (owner: People Analytics)

raw_salesforce / raw_netsuite / raw_usage          raw_hris                     <- synthetic CSV seeds
        │                                                │
   staging/        views, one per source table      people_staging/   private to the people group
        │                                                │
   intermediate/   the business logic                    │
        │            • ACV/TCV + revenue category        │
        │            • monthly ARR spine + waterfall     │
        │            • usage vs entitlement              │
        │            • SFDC <-> NetSuite match           │
        │                                                │
   marts/          star schema (below)  <── keys ──  people/          dim_employee (restricted,
        │                               bridge            │             contract enforced),
        │                                                 │             fct_headcount_monthly
   semantic/       MetricFlow metrics                     ├── secure_<role>/   one view per role,
                                                          │                    generated from the policy
                                                          └── people_metrics/  aggregates, groups < 5 suppressed
```

Policy: [`seeds/governance/access_policy.csv`](seeds/governance/access_policy.csv) ·
roles: [`seeds/governance/roles.csv`](seeds/governance/roles.csv) · the macro that
applies them: [`macros/governance/secure_view.sql`](macros/governance/secure_view.sql).

See **[DATA_MODEL.md](DATA_MODEL.md)** for the ERDs and per-mart build-up DAGs.

### The marts

| Mart | Grain | Purpose |
|---|---|---|
| `dim_account` | account | Conformed customer dimension (geo, division, industry, segment/tier, owner, NetSuite bridge, current ARR). |
| `dim_product` | product | Product hierarchy (line of business → family → product → SKU), recurring flag, NetSuite item bridge. |
| `dim_sales_rep` | rep | Rep, team, region, and the employee key from the people domain's bridge. |
| `fct_acv` | opportunity line | **Sales performance & pipeline.** `acv`, `tcv`, revenue category, by close date. Won + open pipeline. Contract enforced. |
| `fct_arr` | account × product × month | **Recurring run-rate & ARR waterfall.** Movement buckets sum to net new ARR. Contract enforced. |
| `fct_usage` | account × product × month | Consumption vs entitlement; overage / under-utilization signals. |
| `rpt_contract_to_netsuite_recon` | contract ↔ order | Finance reconciliation with discrepancy categories. |

### The people models

| Model | Grain | Access | Purpose |
|---|---|---|---|
| `dim_employee` | person | private | Identity, org, pay against band (compa-ratio), current leave, gender. Every column classified. Contract enforced. |
| `fct_headcount_monthly` | month × department × region | private | Headcount, hires, exits. Private because a small team can be one person. |
| `secure_<role>__employees` | person | public | One view per role (HR, Finance, Sales manager EMEA, Analyst), generated from the policy. |
| `rpt_people__department_summary` | department | public | Headcount, 12-month attrition, pay against band. Groups under 5 suppressed. |
| `rpt_people__pay_equity` | level × gender | public | Gap to men at the same level, and the cost to close it. Groups under 5 suppressed. |
| `rpt_people__revenue_per_employee` | month | public | ARR per employee: the metric that joins the two domains. |
| `bridge_employee_sales_rep` | rep | public | Keys only. How revenue joins people without reading an HR record. |

---

## Key modeling decisions

**ARR vs ACV are deliberately distinct facts, not duplicates.**

| | `fct_arr` (ARR) | `fct_acv` (ACV) |
|---|---|---|
| Question | Recurring run-rate over time + what moved it | Annualized value of each deal sold |
| Grain | account × product × month-end | opportunity line (won + pipeline) |
| Scope | **Recurring only** | Recurring **+ one-time** |
| Time basis | Month-end **measurement date** | **Close date** / sales year |
| Value | Run-rate, annualized (MRR×12) | `acv` = avg annual recurring + frontloaded one-time; `tcv` carried alongside |
| Use | ARR bridge, NRR/GRR, churn | Bookings, pipeline, ASP, win/loss |

*Worked example:* a 3-year deal at $100k/yr recurring + a $10k one-time fee →
**ACV $110k, TCV $310k** (a dbt test asserts `acv = annual_recurring + one_time`).

**ARR is a point-in-time snapshot.** A monthly spine of **month-end measurement
dates** is built with `dbt_utils.date_spine`; each active subscription is stated at
its annual run-rate; the grid is densified per account×product so month-over-month
**churn and reactivation** are detectable.

**Revenue categories** (`new_logo`, `cross_sell`, `upsell`, `downgrade`, `churn`,
`scheduled`) are *derived* from the data on **both** facts — from MoM ARR change at
account×product grain (so upsell vs cross-sell is distinguishable), and from
opportunity type + account/product history on the bookings side.

**The ARR waterfall balances exactly.** For every month,
`sum(ending_arr) = sum(beginning_arr) + Σ(movement buckets)` — enforced by a singular
test, with a companion test that ending ARR is continuous month to month.

**Reconciliation** full-outer-joins contracts to NetSuite orders on
`external_order_ref` and buckets each row (amount mismatch, missing, orphan, timing,
currency rounding, partial billing). A closed-loop test asserts the mart surfaces
exactly the discrepancies the generator seeded.

**Pay equity is measured within level, against the band.** Compa-ratio (salary ÷
band midpoint for the person's level and region) compared across genders *within a
level* is like for like. The company-wide average can look equal while one level
hides a gap, and in this data it does.

**Access is generated, not hand-written.** Each column's `sensitivity` and
`category` live in YAML; `access_policy.csv` maps categories to treatments per role;
`secure_view()` writes each role's SQL. Untagged columns are hidden by default.

---

## Semantic layer (MetricFlow)

`models/semantic/` defines semantic models over the marts and ~20 metrics — `total_arr`,
`net_new_arr`, `new_logo_arr`, `expansion_arr`, `net_revenue_retention`,
`gross_revenue_retention`, `bookings_acv`, `pipeline_acv`, `average_deal_acv`,
`average_utilization`, … — so a metric is defined once and sliced consistently by the
shared `account`, `product`, and `sales_rep` dimensions.

```bash
dbt parse                                            # validates the semantic manifest
mf query --metrics net_revenue_retention --group-by metric_time__year
mf query --metrics bookings_acv --group-by account__segment,metric_time__quarter
```

> The metrics validate via `dbt parse` and the generated SQL executes against the
> warehouse. (On some local Windows setups the `mf` CLI's *result-table renderer*
> has a display bug unrelated to the definitions — the dbt Semantic Layer serves the
> same metrics to BI tools and AI agents.)

This semantic + documentation layer is also what makes the marts consumable by an
**MCP server / AI agent**: every model and column is described. An AI agent gets the
metrics and the `secure_ai_agent` aggregates, never a person-level row.

---

## Tests

`dbt build` runs **132 data tests**:

- **Generic:** `unique` / `not_null` on keys, `relationships` (fact → dim FKs),
  `accepted_values` (revenue categories, statuses, departments), and `dbt_utils`
  `unique_combination_of_columns` / `accepted_range` on fact grains and ratios.
- **Contracts:** `fct_arr`, `fct_acv` and `dim_employee` fail the build if a column's
  name or type changes.
- **Proof tests (in `tests/`), revenue:** ARR waterfall integrity, ARR continuity,
  the ACV identity, and the reconciliation closed-loop count check.
- **Proof tests, governance:** no PII leaks through any secure view; restricted data
  never reaches analysts or the AI agent; row filters hold exactly; no metric for a
  group under 5. See [GOVERNANCE.md](GOVERNANCE.md#the-proof).

After the build, [`scripts/check_governance.py`](scripts/check_governance.py) fails CI
if any model lacks an owner or description, or any personal-looking column lacks a
sensitivity tag.

---

## Portability & layout

- **Warehouse:** DuckDB locally (`profiles.yml`); a BigQuery target is included as a
  commented example. SQL uses ANSI + `dbt_utils` cross-db macros, so it ports cleanly.
  The access controls map to BigQuery grants, row access policies and policy tags in
  [`governance/bigquery/`](governance/bigquery/).
- **`scripts/generate_seeds.py`** and **`scripts/generate_people_seeds.py`** build the
  synthetic data deterministically (fixed seeds) and record what they seeded
  (`seeded_discrepancy_counts.json`, `seeded_people_findings.json`).
- A `generate_schema_name` override keeps schemas readable (`staging`, `marts`,
  `people`, `secure_analyst`, …).
