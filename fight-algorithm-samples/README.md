# The Fight Algorithm — procedural / analytical work samples

[**thefightalgorithm.com**](https://thefightalgorithm.com) is an independent MMA
analytics publication I build and run end-to-end: a Python + DuckDB data pipeline
that scrapes and models ~8,500 UFC fights and 1,800+ fighters, a library of
data-driven articles, and an interactive Next.js site with 50+ custom
visualizations.

It's here as a sample of my work **outside traditional SQL/dbt** — procedural
code, statistics/ML, and interactive data visualization. Three representative,
unmodified files (each with a short header explaining what it shows):

| File | Language | What it demonstrates |
|---|---|---|
| [`article5_model_v2.py`](article5_model_v2.py) | Python / scikit-learn | A full ML pipeline — ~30 engineered features, a **stacking ensemble** (GBM + RF + ExtraTrees + MLP + SVM → logistic meta-learner), probability **calibration**, feature selection, and cross-validated hyperparameter tuning. Predicts fight win % and method (KO/Sub/Decision). |
| [`article17_chin_index.py`](article17_chin_index.py) | Python / SQL (DuckDB) | **Complex analytical SQL** — self-joins to pair combatants within a bout, window functions, CTEs, and deliberate sample-size thresholds — to compute a defensive durability metric across 1,800+ fighters. |
| [`fightSimulator.ts`](fightSimulator.ts) | TypeScript | A typed, pure **Monte Carlo simulation engine** that draws round-by-round outcomes from real per-fighter statistical distributions and computes win probabilities; powers an interactive "simulate a fight" tool. |

## Why these are relevant to a revenue-analytics role

- **The same engineering instincts as the dbt project in this repo**: a clean
  data pipeline (DuckDB here too), explicit and documented methodology, and a
  reproducible path from raw data → metric → published output.
- **Statistics + ML beyond SQL** (the JD's Python / "statistical and machine
  learning packages" bonus) — feature engineering, calibration, and validation
  done with the same rigor I'd bring to forecasting or propensity work in a GTM
  setting.
- **Stakeholder-facing visualization**: the live site is the "dashboard/report"
  sample — radar/bar/heatmap charts, sortable fighter directories, and the
  interactive simulator, all driven by the JSON these scripts export. See the
  [fighters directory](https://thefightalgorithm.com/fighters) and
  [predictions](https://thefightalgorithm.com/predictions).

> These files read from the publication's own DuckDB database, so they're included
> for review rather than to execute standalone.
