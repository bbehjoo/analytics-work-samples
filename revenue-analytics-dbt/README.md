# Revenue Analytics — dbt project (Salesforce + NetSuite → GTM marts)

A production-shaped dbt project that models a B2B SaaS revenue stack — **Salesforce**
(CRM) and **NetSuite** (ERP) — into a star-schema set of **GTM / Revenue data marts**,
with a **MetricFlow semantic layer**, data tests, and full documentation.

It runs locally on **DuckDB** with **synthetic** data (no warehouse, no credentials,
nothing proprietary), and the SQL is kept BigQuery-portable so the same models deploy
to BigQuery by swapping the profile.

> Built as an interview work sample. It mirrors the kind of centralized revenue marts
> I built at Turnitin, rebuilt from scratch on generated data.

📊 **[Live visual report](https://bbehjoo.github.io/analytics-work-samples/)** &nbsp;·&nbsp; 🗺️ **[ERD & lineage diagrams](DATA_MODEL.md)**

---

## Quickstart

```bash
# from this directory (revenue-analytics-dbt/)
python -m venv .venv && source .venv/Scripts/activate   # Windows; use bin/activate on macOS/Linux
pip install -r requirements.txt

python scripts/generate_seeds.py     # deterministic synthetic Salesforce + NetSuite data

dbt deps                             # install dbt_utils
dbt build                            # seeds -> staging -> intermediate -> marts + 97 data tests
dbt docs generate && dbt docs serve  # browse the documented DAG
```

`dbt build` runs the whole pipeline and every test in one command (expect
`PASS=139`). A `grafana.duckdb` file is created in this folder and is git-ignored.

---

## Architecture

```
seeds (raw_salesforce / raw_netsuite / raw_usage)   <- synthetic CSVs, emulate the landed source tables
        │
   staging/        views — one per source table; rename, recast, light cleaning (source() + tests)
        │
   intermediate/   views — the business logic:
        │            • int_opportunity_lines__acv      ACV/TCV math + revenue category (opp-line grain)
        │            • int_contract_lines__normalized  subscription segments + product hierarchy
        │            • int_arr__account_product_month   monthly ARR spine, densified
        │            • int_arr__movements               the ARR waterfall engine (MoM classification)
        │            • int_usage__monthly_rollup        usage aligned to month-end
        │            • int_recon__contract_order_match  SFDC <-> NetSuite match + variances
        │
   marts/          tables — star schema (below)
        │
   models/semantic/  MetricFlow semantic models + metrics on the marts
```

See **[DATA_MODEL.md](DATA_MODEL.md)** for the entity-relationship diagram (how the
marts relate) and a per-mart build-up DAG (how each is assembled from the sources).

### The marts

| Mart | Grain | Purpose |
|---|---|---|
| `dim_account` | account | Conformed customer dimension (geo, division, industry, segment/tier, owner, NetSuite bridge, current ARR). |
| `dim_product` | product | Product hierarchy (LOB → family → product → SKU), recurring flag, NetSuite item bridge. |
| `dim_sales_rep` | rep | Rep, team, region. |
| `fct_acv` | opportunity line | **Sales performance & pipeline.** `acv`, `tcv`, revenue category, by close date. Won + open pipeline. |
| `fct_arr` | account × product × month | **Recurring run-rate & ARR waterfall.** Movement buckets sum to net new ARR. |
| `fct_usage` | account × product × month | Consumption vs entitlement; overage / under-utilization signals. |
| `rpt_contract_to_netsuite_recon` | contract ↔ order | Finance reconciliation with discrepancy categories. |

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
**MCP server / AI agent**: every model and column is described in `schema.yml`.

---

## Tests

`dbt build` runs **97 data tests**:

- **Generic:** `unique` / `not_null` on keys, `relationships` (fact → dim FKs),
  `accepted_values` (revenue categories, statuses), and `dbt_utils`
  `unique_combination_of_columns` / `accepted_range` on fact grains and ratios.
- **Singular (proof tests in `tests/`):** ARR waterfall integrity, ARR continuity,
  the ACV identity, and the reconciliation closed-loop count check.

---

## Portability & layout

- **Warehouse:** DuckDB locally (`profiles.yml`); a BigQuery target is included as a
  commented example. SQL uses ANSI + `dbt_utils` cross-db macros, so it ports cleanly.
- **`scripts/generate_seeds.py`** builds the synthetic data deterministically
  (fixed seed) and prints the seeded reconciliation discrepancy counts.
- A `generate_schema_name` override keeps schemas readable (`staging`, `marts`, …).
