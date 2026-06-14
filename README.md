# Analytics Work Samples — Behrang Behjoo

Two samples of how I build data models and turn them into decisions, assembled for
a Senior Analytics & Insights conversation. Everything here is **synthetic or my own
published work** — nothing proprietary.

---

## 1. [`revenue-analytics-dbt/`](revenue-analytics-dbt/) — GTM / Revenue data marts

A production-shaped **dbt** project that models a B2B SaaS revenue stack —
**Salesforce** (CRM) + **NetSuite** (ERP) — into a star schema of revenue marts, with
a **MetricFlow semantic layer**, data tests, and full documentation. It runs locally
on **DuckDB** with generated data (`dbt build` → `PASS=139`), and the SQL is
BigQuery-portable.

This mirrors the centralized revenue marts I built at Turnitin, rebuilt from scratch
on synthetic data.

📊 **[Live visual report →](https://bbehjoo.github.io/analytics-work-samples/)** &nbsp;·&nbsp; 🗺️ **[Data model & lineage diagrams →](revenue-analytics-dbt/DATA_MODEL.md)**

**What it demonstrates**
- **Layered modeling** — staging → intermediate → marts (dims + facts), the way a
  real warehouse is organized.
- **Hard revenue logic done correctly** — an **ARR waterfall** (new logo / cross-sell
  / upsell / downgrade / churn / scheduled) that **reconciles to the cent**, ACV vs
  ARR modeled as genuinely distinct facts, and a **Salesforce↔NetSuite
  reconciliation** that surfaces real finance discrepancies.
- **Rev-rec & financial-metrics fluency** — NRR/GRR, bookings vs pipeline, ASP,
  contract-to-order reconciliation.
- **Trustworthy data** — 97 dbt tests, including singular "proof" tests that assert
  the waterfall balances and the reconciliation is complete.
- **A semantic + documentation layer** built for self-serve and **AI/MCP**
  consumption (every model and column described; metrics defined once in MetricFlow).
- **Communication** — a stakeholder-ready insights report, as a
  [live visual page](https://bbehjoo.github.io/analytics-work-samples/) and in
  [markdown](revenue-analytics-dbt/reports/revenue_insights_report.md), framing each
  finding as *what it is / why it matters / what to do*.

→ See [revenue-analytics-dbt/README.md](revenue-analytics-dbt/README.md) for the
architecture, the ARR/ACV definitions, and how to run it.

## 2. [`fight-algorithm-samples/`](fight-algorithm-samples/) — beyond SQL

Curated, unmodified files from [**thefightalgorithm.com**](https://thefightalgorithm.com),
an independent MMA analytics publication I build and run: a Python + DuckDB pipeline
over ~8,500 UFC fights powering an interactive Next.js site.

**What it demonstrates** — a scikit-learn **stacking ensemble** with calibration and
cross-validation, **complex analytical SQL** (window functions, self-joins), and a
typed **Monte Carlo simulation engine** in TypeScript — i.e. statistics/ML and
procedural code beyond SQL, plus stakeholder-facing data viz on the live site.

→ See [fight-algorithm-samples/README.md](fight-algorithm-samples/README.md).

---

### A note on the data
All data in the dbt project is **synthetic**, generated deterministically by
[`generate_seeds.py`](revenue-analytics-dbt/scripts/generate_seeds.py) (Salesforce +
NetSuite records, with reconciliation discrepancies intentionally seeded so the
recon mart has something to find). The Fight Algorithm files are my own published work.
