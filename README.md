# Data Leadership Work Samples — Behrang Behjoo

[![build](https://github.com/bbehjoo/analytics-work-samples/actions/workflows/ci.yml/badge.svg)](https://github.com/bbehjoo/analytics-work-samples/actions/workflows/ci.yml)

Two samples of how I build and own data: models, governance, and the decisions
they support. Everything here is **synthetic or my own published work** — nothing
proprietary.

---

## 1. [`saas-data-platform/`](saas-data-platform/) — B2B SaaS data platform: revenue, people, and who sees what

A production-shaped **dbt** project that models one B2B SaaS company end to end:
the revenue stack — **Salesforce** (CRM + CPQ) + **NetSuite** (ERP) + product usage — and
the **HRIS** (people, pay, leave), with a **MetricFlow semantic layer**, governed
access to personal data, data tests, and full documentation. It runs locally on
**DuckDB** with generated data (`dbt build` → `PASS=252`), the SQL is
BigQuery-portable, and CI rebuilds and re-tests everything on every push.

It mirrors the revenue marts I've built in B2B SaaS, rebuilt from scratch on
synthetic data, plus the people data and access controls a data leader is
accountable for.

📊 **[Live site →](https://bbehjoo.github.io/analytics-work-samples/)** &nbsp;·&nbsp; 🧭 **[Lineage, layers & ERDs →](https://bbehjoo.github.io/analytics-work-samples/architecture.html)** &nbsp;·&nbsp; 🗺️ **[Data model diagrams →](saas-data-platform/DATA_MODEL.md)** &nbsp;·&nbsp; 🔐 **[Governance →](saas-data-platform/GOVERNANCE.md)**

**What it demonstrates**
- **Layered modeling** — sources → staging → intermediate → marts (dims + facts) →
  serving, the way a real warehouse is organized, with every layer tested.
- **Hard revenue logic done correctly** — an **ARR waterfall** (new logo / cross-sell
  / upsell / downgrade / churn / scheduled) that **reconciles to the cent**, ACV vs
  ARR modeled as genuinely distinct facts, and a **Salesforce↔NetSuite
  reconciliation** that surfaces real finance discrepancies.
- **Quote to cash, end to end** — CPQ quotes priced off regional price books,
  list-to-net discounting, and approvals for discounts above policy; every
  primary quote ties to its booking to the cent, and one report follows each
  deal from quote → booking → contract → ERP order → invoice.
- **Sensitive data governed by design** — every column about a person (PII, pay,
  health/PHI, demographics) is classified; **one policy file** generates a secure
  view per role (HR, Finance, Sales manager, Analyst, AI agent) with masking,
  pseudonymization, banding and row-level filters; groups under 5 are suppressed.
- **Proof, not promises** — 173 dbt tests, including 11 singular "proof" tests that
  assert the waterfall balances, the reconciliation is complete, quotes tie to
  bookings, every discount above policy is caught, **no PII leaks** through any
  view, and pay, health and gender never reach analysts or AI.
- **Ownership** — every model has a named owning team, certified models have
  **enforced contracts**, and a governance check fails CI if ownership or
  classification slips. The same access rules map to BigQuery grants, row access
  policies and policy tags for production.
- **A semantic + documentation layer** built for self-serve and **AI/MCP**
  consumption — every model and column described, metrics defined once, and AI
  agents limited to governed aggregates.
- **Communication** — a revenue review and a people review as a
  [live visual site](https://bbehjoo.github.io/analytics-work-samples/) and in
  [markdown](saas-data-platform/reports/), framing each finding as
  *what it is / why it matters / what to do*.

→ See [saas-data-platform/README.md](saas-data-platform/README.md) for the
architecture, the ARR/ACV definitions, the access model, and how to run it.

## 2. [`fight-algorithm-samples/`](fight-algorithm-samples/) — beyond SQL

Curated, unmodified files from [**thefightalgorithm.com**](https://thefightalgorithm.com),
an independent MMA analytics publication I build and run: a Python + DuckDB pipeline
over ~8,500 UFC fights powering an interactive Next.js site.

**What it demonstrates** — a scikit-learn **stacking ensemble** with calibration and
cross-validation, **complex analytical SQL** (window functions, self-joins), and a
typed **Monte Carlo simulation engine** in TypeScript — i.e. statistics/ML and
procedural code beyond SQL, plus a product I own from pipeline to published page.

→ See [fight-algorithm-samples/README.md](fight-algorithm-samples/README.md).

---

### A note on the data
All data in the dbt project is **synthetic**, generated deterministically by
[`generate_seeds.py`](saas-data-platform/scripts/generate_seeds.py) (Salesforce,
NetSuite and usage records, with reconciliation discrepancies intentionally seeded
so the recon mart has something to find) and
[`generate_people_seeds.py`](saas-data-platform/scripts/generate_people_seeds.py)
(HRIS records for invented people, with a pay gap and an attrition hotspot seeded
so the people reports have something to find). The Fight Algorithm files are my own
published work.
