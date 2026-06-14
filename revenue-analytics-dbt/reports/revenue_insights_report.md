# Revenue Insights — Quarterly Business Review (sample)

> 📊 A **visual, charted version** of this report sits beside this file as
> [`revenue_insights_report.html`](revenue_insights_report.html) and is published at
> **[bbehjoo.github.io/analytics-work-samples](https://bbehjoo.github.io/analytics-work-samples/)**
> — both generated from the marts by [`scripts/build_report.py`](../scripts/build_report.py).

*Built entirely on the marts in this dbt project, against synthetic Salesforce +
NetSuite data. Every figure below is reproducible — the source mart/metric is
named under each finding, and the two `analyses/` queries (`arr_bridge_by_quarter`,
`recon_summary`) generate the headline tables. This is a work sample: the goal is
to show how I turn a data model into a "what it is / why it matters / what to do"
narrative for GTM and Finance leadership.*

---

## Executive summary

- **ARR grew from ~$1.5M to $82.1M** over three years. Growth is **healthy but
  decelerating** — net new ARR was $30.8M (2023) → $26.2M (2024) → $25.1M (2025).
- The growth **engine is shifting from new logo to expansion**. New-logo ARR fell
  from $29.7M to $14.5M, while expansion (upsell + cross-sell) rose from $1.2M to
  **$20.3M** — land-and-expand is maturing exactly as it should.
- **Churn is the emerging risk.** Gross churn grew from ~$0 to **-$8.3M** in 2025.
  Net Revenue Retention is **101%** and Gross Revenue Retention **99%** — retention
  is holding, but the churn trend needs ownership before it outpaces expansion.
- **~31% of subscriptions are consuming over their entitlement** — a quantified,
  addressable expansion pipeline. Another **~10% are under-utilized** (churn risk).
- **Finance hygiene: $2.2M of signed contracts have no NetSuite order**, plus
  $0.4M of order-amount mismatches. This is a clean, prioritized close-the-books list.

---

## 1. The ARR bridge — where growth comes from

**What it is.** The company ARR waterfall: how each year's beginning ARR turns into
ending ARR through new logo, expansion, downgrade, and churn. *(Source: `fct_arr`;
query: `analyses/arr_bridge_by_quarter.sql`.)*

| Year | New logo | Expansion | Downgrade | Churn | Net new ARR | Ending ARR |
|-----:|---------:|----------:|----------:|------:|------------:|-----------:|
| 2023 | $29.7M | $1.2M | -$0.1M | $0.0M | **$30.8M** | $30.8M |
| 2024 | $23.4M | $5.8M | -$0.4M | -$2.6M | **$26.2M** | $57.0M |
| 2025 | $14.5M | $20.3M | -$1.3M | -$8.3M | **$25.1M** | **$82.1M** |

**Why it matters.** The mix is moving in the right direction — expansion went from
4% of net new ARR to ~80% — but two lines need attention: **new-logo is shrinking**
and **churn is accelerating**. Net new ARR is flat only because expansion is masking
both.

**What to do.** (1) Pressure-test the new-logo top of funnel — is it pipeline
volume or win-rate? (2) Stand up a churn early-warning using §3 below; a 2-point
improvement in GRR is worth ~$1.6M/yr at current scale.

> *The waterfall is verified by a dbt test: for every month,
> `sum(ending_arr) = sum(beginning_arr) + Σ(movements)` — it reconciles to the cent.*

---

## 2. Retention — NRR and GRR

**What it is.** Net and Gross Revenue Retention derived from the ARR movement
buckets. *(Source: `fct_arr` movement columns; metrics `net_revenue_retention`,
`gross_revenue_retention`.)*

| Metric | Value | Read |
|---|---:|---|
| Gross Revenue Retention | **99.2%** | Very low contraction+churn losses today… |
| Net Revenue Retention | **100.9%** | …but expansion is only just offsetting them |

**Why it matters.** NRR barely above 100% means the install base is roughly
self-sustaining but not yet a growth engine on its own. With churn accelerating
(§1), NRR is the metric most at risk next year.

**What to do.** Segment NRR by `dim_account.segment` and `dim_product.line_of_business`
(both are conformed dimensions on `fct_arr`) to find which cohorts are dragging it —
then target expansion plays at the high-utilization accounts in §3.

---

## 3. Usage vs entitlement — a quantified expansion & churn list

**What it is.** Monthly consumption compared to the subscription entitlement in
force. *(Source: `fct_usage`.)*

| Signal | Share of account-months | Action |
|---|---:|---|
| **Over entitlement** (utilization > 100%) | **31.1%** | Expansion / upsell pipeline |
| Healthy (50–100%) | 59.1% | Monitor |
| **Under-utilized** (< 50%) | **9.8%** | Churn / downsell risk |

**Why it matters.** Expansion is now the primary growth lever (§1), and this is the
data that operationalizes it: ~31% of subscriptions are already over-consuming what
they pay for — a warm, evidence-backed upsell list — while ~10% are barely using the
product ahead of renewal.

**What to do.** Route over-entitlement accounts to AMs as expansion plays; route
under-utilized accounts approaching `contract_end_date` to CS for intervention.

---

## 4. Bookings & pipeline — the sales view

**What it is.** ACV at opportunity-line grain, by close date. Distinct from ARR:
includes one-time services and renewals, and is measured at the sales motion.
*(Source: `fct_acv`; metrics `bookings_acv`, `pipeline_acv`, `average_deal_acv`.)*

- **Closed-won bookings ACV (all-time): $188M** — of which new logo $69M, expansion
  $27M, renewals (scheduled) $94M, downgrades -$2M.
- **Open pipeline ACV: $17.9M across 83 opportunities.**
- Bookings by segment: **Mid-Market $76.7M** (265 deals), SMB $64.1M (219), Enterprise
  $47.3M (170); blended ASP ~$0.29M.

**Why it matters.** Renewals are the largest single bookings category — protecting
the renewal base is as important as new sales. Mid-Market is the bookings volume
engine.

**What to do.** Track pipeline-ACV coverage against the new-logo gap from §1, and
watch renewal bookings as the leading indicator of the §1 churn line.

---

## 5. Finance hygiene — Salesforce ↔ NetSuite reconciliation

**What it is.** Every contract matched to its NetSuite order and invoices, with the
disagreements bucketed. *(Source: `rpt_contract_to_netsuite_recon`; query:
`analyses/recon_summary.sql`.)*

| Discrepancy | Count | $ at risk | What it means |
|---|---:|---:|---|
| **Missing in NetSuite** | 8 | **$2.22M** | Signed contracts never ordered in the ERP |
| **Amount mismatch** | 15 | $0.41M | Contract value ≠ order value (> $50 and > 1%) |
| **Orphan in NetSuite** | 5 | $0.21M | ERP orders with no Salesforce contract |
| Currency rounding | 6 | $152 | Immaterial; can be auto-cleared |
| Timing difference | 10 | — | Amounts tie; order booked 15–50 days late |
| Partially invoiced | 12 | — | Billed < ordered (revenue not yet invoiced) |

**Why it matters.** The "missing in NetSuite" bucket is **$2.2M of revenue that is
contracted but not represented in finance** — a direct close-the-books and
revenue-recognition risk, not a rounding nuisance.

**What to do.** Work the 8 missing + 5 orphan records first (highest $ and clearest
fix), auto-clear the currency-rounding bucket with a materiality threshold, and make
this report a standing month-end checklist.

> *This whole report is closed-loop tested: a dbt test asserts the reconciliation
> surfaces exactly the discrepancies present in the source data.*

---

*Reproduce: `dbt build` then `dbt compile` the `analyses/` queries (or open the
marts in any SQL client). Metric values come from the marts and the MetricFlow
semantic layer in `models/semantic/`.*
