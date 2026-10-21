# People Insights: year-end review (sample)

> A **visual version** of this report is published at
> **[bbehjoo.github.io/analytics-work-samples/people.html](https://bbehjoo.github.io/analytics-work-samples/people.html)**,
> generated from the marts by [`scripts/build_site.py`](../scripts/build_site.py).

*Built on the people marts in this dbt project, against synthetic HRIS data, as of
31 Dec 2025. Every figure comes from `people_metrics`, the shareable layer where
any group under 5 people is suppressed, so nothing here describes an individual.
Same format as the [revenue report](revenue_insights_report.md): what it is, why it
matters, what to do.*

---

## Executive summary

- **ARR per employee peaked at $226k in June 2025 and slipped back to $208k by
  December.** Headcount grew 18% in the second half while ARR grew 9%.
- **Customer Success loses 31% of its people a year**, three times the company
  rate of 11%, and every exit in 2025 was voluntary. It is the team that owns
  renewals, in the year churn tripled to $8.5M.
- **Company-wide, women and men are paid the same on average. At L4 they are
  not**: women are paid 6.4% less than men against the same pay band. Closing it
  costs about $345k a year, 0.7% of base payroll.

---

## 1. ARR per employee: efficiency stalled in 2025

**What it is.** Company ARR divided by headcount at each month-end. The one number
that joins the revenue and people domains. *(Source: `rpt_people__revenue_per_employee`.)*

| Month-end | ARR | Headcount | ARR per employee |
|---|---:|---:|---:|
| Dec 2023 | $30.6M | 190 | $161k |
| Dec 2024 | $57.8M | 285 | $203k |
| Jun 2025 | $78.6M | 348 | **$226k** |
| Dec 2025 | $85.7M | 412 | $208k |

**Why it matters.** Each new hire supported more ARR through 2024 and the first
half of 2025. In the second half the company added 64 people (348 to 412) while
ARR grew by $7.1M. Efficiency is back near where it was a year ago.

**What to do.** Use ARR per employee as a guardrail on the 2026 hiring plan: approve
headcount against planned ARR so the ratio holds at $205k or better, and review it
monthly next to the ARR bridge.

---

## 2. Attrition: Customer Success is the hotspot

**What it is.** Exits in the last twelve months divided by average headcount, by
department. *(Source: `rpt_people__department_summary`.)*

| Department | Headcount | Attrition (12 mo) | Voluntary | Pay vs band |
|---|---:|---:|---:|---:|
| **Customer Success** | 36 | **30.7%** | **30.7%** | 1.00 |
| Engineering | 138 | 10.9% | 6.7% | 0.99 |
| Marketing | 36 | 9.4% | 9.4% | 1.00 |
| Product | 39 | 8.4% | 5.6% | 1.00 |
| Sales | 114 | 7.3% | 6.3% | 0.99 |
| Finance | 19 | 6.6% | 6.6% | 1.01 |
| People | 27 | 4.9% | 4.9% | 0.99 |
| Legal | fewer than 5 | suppressed | suppressed | suppressed |
| **Company** | **412** | **10.7%** | **8.8%** | |

**Why it matters.** Customer Success owns renewals, and churn went from $2.7M in
2024 to $8.5M in 2025 (see the revenue report). The two may be linked, but this
data can't show it yet. Pay isn't the obvious cause: Customer Success is paid at
the band midpoint, the same as everyone else.

**What to do.** Run stay interviews in Customer Success this quarter. Then add the
missing join: which CSM owns which account. With it, the next version of this
report can test whether accounts that lost their CSM churned more.

> *Legal has three people, so its row shows no numbers. The suppression is
> enforced by a test, not by care: `assert_small_groups_suppressed`.*

---

## 3. Pay equity: the average hides a gap at L4

**What it is.** Compa-ratio (base salary divided by the band midpoint for the
person's level and region) by level and gender. Comparing within a level and
against the same band makes it like for like. *(Source: `rpt_people__pay_equity`.)*

| Level | Women vs men | Women (n) |
|---|---:|---:|
| L1 | +1.9% | 9 |
| L2 | -0.1% | 25 |
| L3 | +0.6% | 50 |
| **L4** | **-6.4%** | **43** |
| L5 | +0.9% | 40 |
| L6 | -2.3% | 12 |
| L7 | suppressed | fewer than 5 |

**Why it matters.** Across the company, women average $116.1k and men $116.6k, so
the headline looks fine. At L4, women sit at 0.943 of their band midpoint and men
at 1.008. That's a pay-equity exposure that a company-wide average would never
surface.

**What to do.** Close the L4 gap in the next comp cycle: raising the 43 women to the
men's average compa-ratio costs about $345k a year, 0.7% of base
payroll (`cost_to_close_usd`). Watch L6 (-2.3%) at the next cycle. Make this level-by-gender check a
standing step in every comp review; this report is that check.

---

*Reproduce: `dbt build`, then query `people_metrics.*` in `warehouse.duckdb`. Nothing
in this report needs access to a person-level row.*
