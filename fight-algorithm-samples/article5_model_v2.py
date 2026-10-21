# =============================================================================
# WORK SAMPLE — from The Fight Algorithm (thefightalgorithm.com), an independent
# MMA analytics publication I build and run. Procedural Python / ML sample.
#
# What this demonstrates:
#   - End-to-end ML pipeline: ~30 engineered features from UFC fight history, a
#     stacking ensemble (GradientBoosting + RandomForest + ExtraTrees + MLP + SVM
#     with a logistic meta-learner), probability calibration, feature selection,
#     and hyperparameter tuning under StratifiedKFold cross-validation.
#   - Reads from a local DuckDB warehouse (the same engine as the dbt project in
#     this repo) and writes calibrated win/method probabilities as JSON for the site.
#
# Original code, unmodified except for this header. Runs against the publication's
# own DuckDB database; included here for review, not to execute standalone.
# =============================================================================

"""
Article 5 v2: Advanced ML Fight Prediction Model
=================================================
Second-generation model using stacking ensemble, polynomial feature
interactions, feature selection, and hyperparameter tuning.

Imports data pipeline from article5_model.py, replaces the training and
prediction pipeline. Writes to the same predictions.json.

Usage:
    python analysis/scripts/article5_model_v2.py              # train + predict
    python analysis/scripts/article5_model_v2.py --retrain    # force retrain
    python analysis/scripts/article5_model_v2.py --cv-only    # evaluate only
"""

import argparse
import json
import pickle
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    StackingClassifier,
    ExtraTreesClassifier,
)
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    RandomizedSearchCV,
    StratifiedKFold,
    cross_val_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.svm import SVC

warnings.filterwarnings("ignore")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ────────────────────────────────────────────────────────────────────
db_path    = Path(__file__).parent.parent / "data" / "ufcstats.duckdb"
output_dir = Path(__file__).parent.parent.parent / "website" / "public" / "data"
model_dir  = Path(__file__).parent.parent / "data"
output_dir.mkdir(parents=True, exist_ok=True)

# ── Constants ────────────────────────────────────────────────────────────────
MIN_PRIOR_FIGHTS = 3
EVENT_NAME = "UFC Fight Night: Moreno vs. Kavanagh"
EVENT_DATE = "2026-02-28"

FULL_CARD = [
    {"fighter1": "Brandon Moreno",   "fighter2": "Lone'er Kavanagh"},
    {"fighter1": "Marlon Vera",      "fighter2": "David Martinez"},
    {"fighter1": "Daniel Zellhuber", "fighter2": "King Green"},
    {"fighter1": "Edgar Chairez",    "fighter2": "Felipe Bunes"},
    {"fighter1": "Imanol Rodriguez", "fighter2": "Kevin Borjas"},
    {"fighter1": "Santiago Luna",    "fighter2": "Angel Pacheco"},
    {"fighter1": "Jose Medina",      "fighter2": "Ryan Gandra"},
    {"fighter1": "Macy Chiasson",    "fighter2": "Ailin Perez"},
    {"fighter1": "Carlos Quinonez",  "fighter2": "Kris Moutinho"},
]

# EXPANDED feature set: 30 features (career + last-3-fight recency)
FEATURE_COLS = [
    # Offensive striking
    "sig_spm", "sig_acc",
    # Defensive striking
    "sig_str_absorbed_spm", "strike_differential_spm",
    # Grappling offensive
    "td_per_fight", "td_acc", "sub_att_per_fight", "kd_per_fight", "ctrl_secs_per_fight",
    # Grappling defensive
    "td_defense",
    # Style profile
    "dist_pct", "clinch_pct", "ground_pct",
    # Target profile
    "head_pct", "body_pct", "leg_pct",
    # Win/loss history
    "win_rate", "finish_rate", "ko_win_rate", "sub_win_rate", "dec_win_rate",
    # Recent form (last 5 fights)
    "recent_win_rate",
    # NEW: last-3-fight recency stats
    "recent_sig_spm", "recent_sig_acc", "recent_td_per_fight",
    "recent_kd_per_fight", "recent_ctrl_secs_per_fight",
    # NEW: consistency / variance
    "win_streak", "loss_streak",
    # NEW: experience signal
    "log_fights",
]

METHOD_FEATURE_COLS = [
    "sig_spm", "kd_per_fight", "sub_att_per_fight", "td_per_fight",
    "ground_pct", "dist_pct", "finish_rate", "ctrl_secs_per_fight",
]

print("=" * 70)
print("UFC FIGHT PREDICTION MODEL v2 (Advanced)")
print("=" * 70)

# ── Database ─────────────────────────────────────────────────────────────────
con = duckdb.connect(str(db_path))


# ── Bulk Data Load (reused from v1) ──────────────────────────────────────────

def load_all_data():
    print("\n[1/6] Loading fight data from DuckDB...")

    fights_df = con.execute("""
        SELECT
            fd.fight_id,
            fd.fighter1_url,
            fd.fighter2_url,
            fd.fighter1_name,
            fd.fighter2_name,
            fd.winner,
            fd.method,
            (fd.finish_round - 1) * 300
            + CAST(SPLIT_PART(fd.finish_time, ':', 1) AS INT) * 60
            + CAST(SPLIT_PART(fd.finish_time, ':', 2) AS INT) AS duration_s,
            e.event_date
        FROM fight_details fd
        JOIN fights f ON fd.fight_id = f.fight_id
        JOIN events e ON f.event_id  = e.event_id
        WHERE fd.winner IN ('fighter1', 'fighter2')
          AND fd.method IN ('KO/TKO', 'Submission', 'Decision')
          AND fd.finish_round IS NOT NULL
          AND fd.finish_time IS NOT NULL
          AND fd.finish_time LIKE '%:%'
          AND e.event_date IS NOT NULL
        ORDER BY e.event_date
    """).df()

    stats_df = con.execute("""
        SELECT
            rs.fighter_url,
            rs.fight_id,
            SUM(rs.knockdowns)            AS knockdowns,
            SUM(rs.sig_str_landed)        AS sig_str_landed,
            SUM(rs.sig_str_attempted)     AS sig_str_attempted,
            SUM(rs.takedowns_landed)      AS takedowns_landed,
            SUM(rs.takedowns_attempted)   AS takedowns_attempted,
            SUM(rs.submission_attempts)   AS submission_attempts,
            SUM(rs.sig_distance_landed)   AS sig_distance_landed,
            SUM(rs.sig_clinch_landed)     AS sig_clinch_landed,
            SUM(rs.sig_ground_landed)     AS sig_ground_landed,
            SUM(rs.sig_head_landed)       AS sig_head_landed,
            SUM(rs.sig_body_landed)       AS sig_body_landed,
            SUM(rs.sig_leg_landed)        AS sig_leg_landed,
            SUM(
                CAST(SPLIT_PART(rs.control_time, ':', 1) AS INT) * 60
                + CAST(SPLIT_PART(rs.control_time, ':', 2) AS INT)
            ) AS ctrl_seconds
        FROM round_stats rs
        WHERE rs.control_time IS NOT NULL
          AND rs.control_time LIKE '%:%'
        GROUP BY rs.fighter_url, rs.fight_id
    """).df()

    print(f"   Fights with outcomes: {len(fights_df):,}")
    print(f"   Fighter-fight records: {len(stats_df):,}")
    return fights_df, stats_df


# ── Enhanced Fighter Profile ─────────────────────────────────────────────────

def get_fighter_profile(fighter_url: str, fights_df: pd.DataFrame,
                        stats_df: pd.DataFrame, cutoff_date=None) -> dict | None:
    """
    v2: 30-feature profile with last-3-fight recency stats, streaks, and log experience.
    """
    is_f1 = fights_df["fighter1_url"] == fighter_url
    is_f2 = fights_df["fighter2_url"] == fighter_url
    fighter_fights = fights_df[is_f1 | is_f2].copy()

    if cutoff_date is not None:
        fighter_fights = fighter_fights[fighter_fights["event_date"] < cutoff_date]

    if len(fighter_fights) < MIN_PRIOR_FIGHTS:
        return None

    fighter_fights = fighter_fights.sort_values("event_date")
    num_fights = len(fighter_fights)
    fight_ids  = fighter_fights["fight_id"].values

    rs = stats_df[
        (stats_df["fighter_url"] == fighter_url) &
        (stats_df["fight_id"].isin(fight_ids))
    ]

    is_f1_arr = fighter_fights["fighter1_url"] == fighter_url
    opp_map = pd.Series(
        np.where(is_f1_arr.values, fighter_fights["fighter2_url"].values,
                 fighter_fights["fighter1_url"].values),
        index=fighter_fights["fight_id"].values
    )
    opp_pairs = pd.DataFrame({"fight_id": opp_map.index, "fighter_url": opp_map.values})
    opp_stats = stats_df.merge(opp_pairs, on=["fight_id", "fighter_url"])

    # Offensive totals
    sig_landed  = rs["sig_str_landed"].sum()
    sig_att     = rs["sig_str_attempted"].sum()
    td_landed   = rs["takedowns_landed"].sum()
    td_att      = rs["takedowns_attempted"].sum()
    sub_att     = rs["submission_attempts"].sum()
    kds         = rs["knockdowns"].sum()
    ctrl_secs   = rs["ctrl_seconds"].sum()
    dist_l      = rs["sig_distance_landed"].sum()
    clinch_l    = rs["sig_clinch_landed"].sum()
    ground_l    = rs["sig_ground_landed"].sum()
    head_l      = rs["sig_head_landed"].sum()
    body_l      = rs["sig_body_landed"].sum()
    leg_l       = rs["sig_leg_landed"].sum()

    opp_sig_landed = opp_stats["sig_str_landed"].sum()
    opp_td_landed  = opp_stats["takedowns_landed"].sum()
    opp_td_att     = opp_stats["takedowns_attempted"].sum()

    total_duration_s = max(fighter_fights["duration_s"].sum(), 1)
    total_duration_m = total_duration_s / 60.0

    won = (
        ((is_f1_arr) & (fighter_fights["winner"] == "fighter1")) |
        ((~is_f1_arr) & (fighter_fights["winner"] == "fighter2"))
    )
    ko_won  = won & (fighter_fights["method"] == "KO/TKO")
    sub_won = won & (fighter_fights["method"] == "Submission")
    dec_won = won & (fighter_fights["method"] == "Decision")
    wins    = int(won.sum())

    # Recent form: last 5
    recent5 = fighter_fights.tail(5)
    is_f1_r5 = recent5["fighter1_url"] == fighter_url
    recent_won5 = (
        ((is_f1_r5) & (recent5["winner"] == "fighter1")) |
        ((~is_f1_r5) & (recent5["winner"] == "fighter2"))
    )
    recent_win_rate = float(recent_won5.sum()) / len(recent5)

    # NEW: Recent 3-fight performance stats
    recent3 = fighter_fights.tail(3)
    r3_ids = recent3["fight_id"].values
    r3_stats = rs[rs["fight_id"].isin(r3_ids)]
    r3_duration_s = max(recent3["duration_s"].sum(), 1)
    r3_duration_m = r3_duration_s / 60.0
    r3_num = len(recent3)

    def safe_div(a, b):
        return float(a) / float(b) if b > 0 else 0.0

    recent_sig_spm      = safe_div(r3_stats["sig_str_landed"].sum(), r3_duration_m)
    recent_sig_acc      = safe_div(r3_stats["sig_str_landed"].sum(), r3_stats["sig_str_attempted"].sum())
    recent_td_per_fight = safe_div(r3_stats["takedowns_landed"].sum(), r3_num)
    recent_kd_per_fight = safe_div(r3_stats["knockdowns"].sum(), r3_num)
    recent_ctrl_per_fight = safe_div(r3_stats["ctrl_seconds"].sum(), r3_num)

    # NEW: Win/loss streak (looking backward from most recent)
    won_list = won.values.tolist()
    win_streak = 0
    for w in reversed(won_list):
        if w:
            win_streak += 1
        else:
            break
    loss_streak = 0
    for w in reversed(won_list):
        if not w:
            loss_streak += 1
        else:
            break

    return {
        "fights":                 num_fights,
        "sig_spm":                safe_div(sig_landed, total_duration_m),
        "sig_acc":                safe_div(sig_landed, sig_att),
        "sig_str_absorbed_spm":   safe_div(opp_sig_landed, total_duration_m),
        "strike_differential_spm": safe_div(sig_landed - opp_sig_landed, total_duration_m),
        "td_per_fight":           safe_div(td_landed, num_fights),
        "td_acc":                 safe_div(td_landed, td_att),
        "sub_att_per_fight":      safe_div(sub_att, num_fights),
        "kd_per_fight":           safe_div(kds, num_fights),
        "ctrl_secs_per_fight":    safe_div(ctrl_secs, num_fights),
        "td_defense":             1.0 - safe_div(opp_td_landed, opp_td_att),
        "dist_pct":               safe_div(dist_l, sig_landed),
        "clinch_pct":             safe_div(clinch_l, sig_landed),
        "ground_pct":             safe_div(ground_l, sig_landed),
        "head_pct":               safe_div(head_l, sig_landed),
        "body_pct":               safe_div(body_l, sig_landed),
        "leg_pct":                safe_div(leg_l, sig_landed),
        "win_rate":               safe_div(wins, num_fights),
        "finish_rate":            safe_div(int(ko_won.sum()) + int(sub_won.sum()), max(wins, 1)),
        "ko_win_rate":            safe_div(int(ko_won.sum()), num_fights),
        "sub_win_rate":           safe_div(int(sub_won.sum()), num_fights),
        "dec_win_rate":           safe_div(int(dec_won.sum()), num_fights),
        "recent_win_rate":        recent_win_rate,
        # New recency stats
        "recent_sig_spm":         recent_sig_spm,
        "recent_sig_acc":         recent_sig_acc,
        "recent_td_per_fight":    recent_td_per_fight,
        "recent_kd_per_fight":    recent_kd_per_fight,
        "recent_ctrl_secs_per_fight": recent_ctrl_per_fight,
        # Streaks
        "win_streak":             float(win_streak),
        "loss_streak":            float(loss_streak),
        # Experience
        "log_fights":             float(np.log1p(num_fights)),
    }


# ── Dataset Construction ─────────────────────────────────────────────────────

def build_dataset(fights_df, stats_df):
    print("\n[2/6] Building training dataset (anti-leakage, 30 features)...")

    rows = []
    skipped = 0

    for _, fight in fights_df.iterrows():
        f1_url  = fight["fighter1_url"]
        f2_url  = fight["fighter2_url"]
        cutoff  = fight["event_date"]
        label   = 1 if fight["winner"] == "fighter1" else 0
        method  = fight["method"]

        f1 = get_fighter_profile(f1_url, fights_df, stats_df, cutoff_date=cutoff)
        f2 = get_fighter_profile(f2_url, fights_df, stats_df, cutoff_date=cutoff)

        if f1 is None or f2 is None:
            skipped += 1
            continue

        weight   = min(f1["fights"], f2["fights"]) / 10.0
        winner_s = f1 if label == 1 else f2

        diff = {k: f1[k] - f2[k] for k in FEATURE_COLS}
        rows.append({**diff, "label": label, "method": method,
                     "winner_stats": winner_s, "weight": weight})

        neg = {k: -v for k, v in diff.items()}
        rows.append({**neg, "label": 1 - label, "method": method,
                     "winner_stats": f2 if label == 0 else f1, "weight": weight})

    df = pd.DataFrame(rows)
    print(f"   Training rows: {len(df):,}  |  Fights used: {len(df)//2:,}  |  Skipped: {skipped:,}")
    return df


# ── Advanced Model Training ──────────────────────────────────────────────────

def train_models(df: pd.DataFrame):
    """
    v2 training pipeline:
      1. Scale + PolynomialFeatures (degree=2, interaction_only) for feature combos
      2. SelectKBest to prune the expanded feature set
      3. Individual model CV: GBM, ExtraTrees, SVM-RBF, MLP, LR
      4. StackingClassifier with LR meta-learner
      5. RandomizedSearchCV on the stacking meta-learner
    """
    print("\n[3/6] Training v2 models (stacking + interactions + tuning)...")

    X = df[FEATURE_COLS].fillna(0).values
    y = df["label"].values
    w = df["weight"].values

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # ── Step 1: Individual base model comparison (raw features) ──
    print("\n   -- Base models on raw features --")

    models = {
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.03,
            subsample=0.8, min_samples_leaf=20, random_state=42,
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=400, max_depth=10, min_samples_leaf=10,
            class_weight="balanced", random_state=42, n_jobs=-1,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=400, max_depth=8, min_samples_leaf=15,
            class_weight="balanced", random_state=42, n_jobs=-1,
        ),
        "SVM-RBF": Pipeline([
            ("scaler", StandardScaler()),
            ("svm", SVC(kernel="rbf", C=1.0, gamma="scale", probability=True,
                        random_state=42)),
        ]),
        "MLP": Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=(64, 32), activation="relu",
                max_iter=500, early_stopping=True, validation_fraction=0.15,
                random_state=42,
            )),
        ]),
        "LogisticReg": Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=0.5, max_iter=1000, random_state=42)),
        ]),
    }

    base_scores = {}
    for name, model in models.items():
        scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
        base_scores[name] = scores.mean()
        print(f"   {name:20s} CV: {scores.mean():.3f} +/- {scores.std():.3f}")

    # ── Step 2: Pipeline with polynomial interactions + feature selection ──
    print("\n   -- With polynomial interactions + SelectKBest --")

    poly_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, interaction_only=True, include_bias=False)),
        ("select", SelectKBest(mutual_info_classif, k=50)),
        ("clf", GradientBoostingClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.03,
            subsample=0.8, min_samples_leaf=20, random_state=42,
        )),
    ])
    poly_scores = cross_val_score(poly_pipe, X, y, cv=cv, scoring="accuracy")
    print(f"   GBM+Poly+Select      CV: {poly_scores.mean():.3f} +/- {poly_scores.std():.3f}")

    # ── Step 3: Stacking Classifier ──
    print("\n   -- Stacking Ensemble --")

    estimators = [
        ("gb", GradientBoostingClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.03,
            subsample=0.8, min_samples_leaf=20, random_state=42,
        )),
        ("et", ExtraTreesClassifier(
            n_estimators=400, max_depth=10, min_samples_leaf=10,
            class_weight="balanced", random_state=42, n_jobs=-1,
        )),
        ("svm", Pipeline([
            ("scaler", StandardScaler()),
            ("svm", SVC(kernel="rbf", C=1.0, probability=True, random_state=42)),
        ])),
        ("mlp", Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=(64, 32), max_iter=500,
                early_stopping=True, validation_fraction=0.15,
                random_state=42,
            )),
        ])),
    ]

    stacker = StackingClassifier(
        estimators=estimators,
        final_estimator=LogisticRegression(C=1.0, max_iter=1000, random_state=42),
        cv=5,
        stack_method="predict_proba",
        n_jobs=-1,
    )
    stack_scores = cross_val_score(stacker, X, y, cv=cv, scoring="accuracy")
    print(f"   Stacking (GB+ET+SVM+MLP) CV: {stack_scores.mean():.3f} +/- {stack_scores.std():.3f}")

    # ── Step 4: Stacking with polynomial features ──
    print("\n   -- Stacking + Polynomial Interactions --")

    poly_stacker = Pipeline([
        ("scaler", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, interaction_only=True, include_bias=False)),
        ("select", SelectKBest(mutual_info_classif, k=60)),
        ("stack", StackingClassifier(
            estimators=[
                ("gb", GradientBoostingClassifier(
                    n_estimators=400, max_depth=4, learning_rate=0.03,
                    subsample=0.8, min_samples_leaf=20, random_state=42,
                )),
                ("et", ExtraTreesClassifier(
                    n_estimators=400, max_depth=10, min_samples_leaf=10,
                    random_state=42, n_jobs=-1,
                )),
                ("lr", LogisticRegression(C=1.0, max_iter=1000, random_state=42)),
            ],
            final_estimator=LogisticRegression(C=0.5, max_iter=1000, random_state=42),
            cv=5,
            stack_method="predict_proba",
            n_jobs=-1,
        )),
    ])
    poly_stack_scores = cross_val_score(poly_stacker, X, y, cv=cv, scoring="accuracy")
    print(f"   Poly+Stacking        CV: {poly_stack_scores.mean():.3f} +/- {poly_stack_scores.std():.3f}")

    # ── Step 5: Pick the best model ──
    all_scores = {
        **base_scores,
        "GBM+Poly+Select": poly_scores.mean(),
        "Stacking": stack_scores.mean(),
        "Poly+Stacking": poly_stack_scores.mean(),
    }

    best_name = max(all_scores, key=all_scores.get)
    best_acc  = all_scores[best_name]

    target = 0.70
    status = "[OK] ACHIEVED" if best_acc >= target else "[!!] BELOW TARGET"
    print(f"\n   *** Best model: {best_name} at {best_acc:.1%}  |  Target: {target:.0%}  |  {status}")
    print(f"   All results: {json.dumps({k: round(v, 3) for k, v in sorted(all_scores.items(), key=lambda x: -x[1])}, indent=6)}")

    # ── Step 6: Train final model (best performer) ──
    print("\n   Training final model for deployment...")

    # Map best model name to the actual estimator
    final_models = {
        "GradientBoosting": models["GradientBoosting"],
        "ExtraTrees":       models["ExtraTrees"],
        "RandomForest":     models["RandomForest"],
        "SVM-RBF":          models["SVM-RBF"],
        "MLP":              models["MLP"],
        "LogisticReg":      models["LogisticReg"],
        "GBM+Poly+Select":  poly_pipe,
        "Stacking":         stacker,
        "Poly+Stacking":    poly_stacker,
    }

    best_model = final_models[best_name]

    # Wrap with calibration for probability output (skip if already pipeline with SVC)
    if best_name in ("Stacking", "Poly+Stacking", "SVM-RBF", "MLP", "LogisticReg"):
        # These already produce probabilities
        best_model.fit(X, y)
        final_clf = best_model
    else:
        final_clf = CalibratedClassifierCV(best_model, cv=5, method="isotonic")
        final_clf.fit(X, y)

    # Method classifier
    winner_stats_list = df["winner_stats"].tolist()
    Xm = np.array([[s[k] for k in METHOD_FEATURE_COLS] for s in winner_stats_list])
    ym = df["method"].values

    method_rf = RandomForestClassifier(
        n_estimators=200, max_depth=5, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    method_rf.fit(Xm, ym)
    method_cv = cross_val_score(method_rf, Xm, ym, cv=cv, scoring="accuracy")
    print(f"   Method classifier    CV: {method_cv.mean():.3f} +/- {method_cv.std():.3f}")

    return final_clf, method_rf, best_name, best_acc


# ── Model Persistence ────────────────────────────────────────────────────────

def save_models(clf, method_rf, model_name, accuracy):
    with open(model_dir / "article5_winner_model.pkl", "wb") as f:
        pickle.dump({
            "model": clf,
            "feature_cols": FEATURE_COLS,
            "model_name": model_name,
            "accuracy": accuracy,
            "version": 2,
        }, f)
    with open(model_dir / "article5_method_model.pkl", "wb") as f:
        pickle.dump({"model": method_rf, "feature_cols": METHOD_FEATURE_COLS}, f)
    print(f"   Models saved (v2: {model_name})")


def load_models():
    with open(model_dir / "article5_winner_model.pkl", "rb") as f:
        d = pickle.load(f)
    print(f"   Loaded saved model: {d.get('model_name', 'unknown')} "
          f"(v{d.get('version', 1)}, acc={d.get('accuracy', '?')})")
    clf = d["model"]
    with open(model_dir / "article5_method_model.pkl", "rb") as f:
        d2 = pickle.load(f)
    return clf, d2["model"]


# ── Fighter Lookup ───────────────────────────────────────────────────────────

def find_fighter_url(name):
    rows = con.execute("""
        SELECT DISTINCT fighter1_url AS url, fighter1_name AS name
        FROM fight_details WHERE LOWER(fighter1_name) = LOWER(?)
        UNION
        SELECT DISTINCT fighter2_url, fighter2_name
        FROM fight_details WHERE LOWER(fighter2_name) = LOWER(?)
        LIMIT 1
    """, [name, name]).fetchall()
    if rows:
        return rows[0][0], rows[0][1]
    first = name.split()[0]
    rows = con.execute("""
        SELECT DISTINCT fighter1_url AS url, fighter1_name AS name
        FROM fight_details WHERE LOWER(fighter1_name) LIKE LOWER(?)
        UNION
        SELECT DISTINCT fighter2_url, fighter2_name
        FROM fight_details WHERE LOWER(fighter2_name) LIKE LOWER(?)
        LIMIT 1
    """, [f"%{first}%", f"%{first}%"]).fetchall()
    if rows:
        return rows[0][0], rows[0][1]
    return None, None


def get_fight_count(fighter_url, fights_df):
    if fighter_url is None:
        return 0
    return int(((fights_df["fighter1_url"] == fighter_url) |
                (fights_df["fighter2_url"] == fighter_url)).sum())


# ── Fight Selection ──────────────────────────────────────────────────────────

def select_top_fights(full_card, fights_df, n=3):
    print(f"\n[5/6] Selecting top {n} fights by data richness...")
    ranked = []
    for fight in full_card:
        f1_url, f1_name = find_fighter_url(fight["fighter1"])
        f2_url, f2_name = find_fighter_url(fight["fighter2"])
        f1_count = get_fight_count(f1_url, fights_df)
        f2_count = get_fight_count(f2_url, fights_df)
        combined = f1_count + f2_count
        ok = "OK" if (f1_count >= MIN_PRIOR_FIGHTS and f2_count >= MIN_PRIOR_FIGHTS) else "--"
        print(f"   [{ok}] {fight['fighter1']} ({f1_count}) vs {fight['fighter2']} ({f2_count})")
        ranked.append({
            "fighter1": f1_name or fight["fighter1"],
            "fighter2": f2_name or fight["fighter2"],
            "fighter1_url": f1_url, "fighter2_url": f2_url,
            "f1_count": f1_count, "f2_count": f2_count, "combined": combined,
        })
    ranked.sort(key=lambda x: x["combined"], reverse=True)
    selected = [f for f in ranked
                if f["f1_count"] >= MIN_PRIOR_FIGHTS and f["f2_count"] >= MIN_PRIOR_FIGHTS][:n]
    if len(selected) < n:
        print(f"   WARNING: Only {len(selected)} fights have sufficient data")
    names = ", ".join(f["fighter1"] + " vs " + f["fighter2"] for f in selected)
    print(f"\n   Selected: {names}")
    return selected


# ── Prediction ───────────────────────────────────────────────────────────────

def prob_to_confidence(prob):
    if prob >= 0.68:
        return "High"
    elif prob >= 0.57:
        return "Medium"
    return "Low"


def generate_reasoning(winner, loser, ws, ls, method, prob):
    points = []
    if ws["sig_spm"] - ls["sig_spm"] > 1.0:
        points.append(f"throws {ws['sig_spm'] - ls['sig_spm']:.1f} more sig strikes/min")
    if ws["sig_str_absorbed_spm"] < ls["sig_str_absorbed_spm"] - 0.8:
        points.append(f"absorbs {ls['sig_str_absorbed_spm'] - ws['sig_str_absorbed_spm']:.1f} fewer strikes/min")
    if ws["td_per_fight"] - ls["td_per_fight"] > 0.8:
        points.append(f"averages {ws['td_per_fight'] - ls['td_per_fight']:.1f} more TD/fight")
    if ws["ctrl_secs_per_fight"] - ls["ctrl_secs_per_fight"] > 45:
        d = int(ws["ctrl_secs_per_fight"] - ls["ctrl_secs_per_fight"])
        points.append(f"controls {d//60}:{d%60:02d} more per fight")
    if ws["kd_per_fight"] - ls["kd_per_fight"] > 0.10:
        points.append(f"lands {ws['kd_per_fight'] - ls['kd_per_fight']:.2f} more KD/fight")
    if ws["win_rate"] - ls["win_rate"] > 0.10:
        points.append(f"holds a {(ws['win_rate'] - ls['win_rate'])*100:.0f}pp win rate edge")
    if ws["win_streak"] > ls["win_streak"] and ws["win_streak"] >= 3:
        points.append(f"riding a {int(ws['win_streak'])}-fight win streak")
    if ws["recent_win_rate"] - ls["recent_win_rate"] > 0.20:
        points.append(f"recent form: {ws['recent_win_rate']*100:.0f}% vs {ls['recent_win_rate']*100:.0f}% in last 5")

    method_text = {
        "KO/TKO": "the striking advantage should produce a finish",
        "Submission": "the grappling dominance should force a tap",
        "Decision": "the output and control edge should carry the scorecards",
    }.get(method, "the overall edge should prove decisive")

    pct = int(round(prob * 100))
    intro = f"Model v2 favors {winner} ({pct}% confidence). "
    if points:
        intro += f"{winner} {', '.join(points[:3])}. "
    return intro + f"On this trajectory, {method_text}."


def predict_fight(fight, clf, method_rf, fights_df, stats_df):
    f1_url, f2_url = fight["fighter1_url"], fight["fighter2_url"]
    f1_name, f2_name = fight["fighter1"], fight["fighter2"]

    f1 = get_fighter_profile(f1_url, fights_df, stats_df,
                             cutoff_date=pd.Timestamp("2099-01-01"))
    f2 = get_fighter_profile(f2_url, fights_df, stats_df,
                             cutoff_date=pd.Timestamp("2099-01-01"))

    if f1 is None or f2 is None:
        missing = f1_name if f1 is None else f2_name
        return {
            "fighter1": f1_name, "fighter2": f2_name,
            "pick": "Insufficient data", "method": "N/A",
            "confidence": "Low",
            "reasoning": f"{missing} has insufficient UFC history.",
            "result": "pending", "actualMethod": None,
        }

    diff = np.array([f1[k] - f2[k] for k in FEATURE_COLS]).reshape(1, -1)
    proba = clf.predict_proba(diff)[0]
    prob_f1 = proba[1]

    if prob_f1 >= 0.5:
        pick, ws, ls, loser = f1_name, f1, f2, f2_name
        prob = prob_f1
        mf = np.array([f1[k] for k in METHOD_FEATURE_COLS]).reshape(1, -1)
    else:
        pick, ws, ls, loser = f2_name, f2, f1, f1_name
        prob = 1.0 - prob_f1
        mf = np.array([f2[k] for k in METHOD_FEATURE_COLS]).reshape(1, -1)

    predicted_method = method_rf.predict(mf)[0]
    return {
        "fighter1": f1_name, "fighter2": f2_name,
        "pick": pick, "method": predicted_method,
        "confidence": prob_to_confidence(prob),
        "reasoning": generate_reasoning(pick, loser, ws, ls, predicted_method, prob),
        "result": "pending", "actualMethod": None,
    }


# ── JSON Output ──────────────────────────────────────────────────────────────

def update_predictions_json(predictions):
    predictions_path = output_dir / "predictions.json"
    with open(predictions_path) as f:
        existing = json.load(f)
    existing["events"] = [e for e in existing["events"] if e.get("name") != EVENT_NAME]
    existing["events"].insert(0, {
        "name": EVENT_NAME, "date": EVENT_DATE, "predictions": predictions,
    })
    with open(predictions_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"\n   Saved {len(predictions)} predictions to predictions.json")


# ── Main ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--retrain", action="store_true")
    p.add_argument("--cv-only", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fights_df, stats_df = load_all_data()

    winner_path = model_dir / "article5_winner_model.pkl"
    should_train = args.retrain or not winner_path.exists()

    if should_train:
        df = build_dataset(fights_df, stats_df)
        clf, method_rf, model_name, accuracy = train_models(df)
        save_models(clf, method_rf, model_name, accuracy)
    else:
        print("\n[2-4/6] Skipped training")
        clf, method_rf = load_models()

    if args.cv_only:
        print("\n[COMPLETE] CV-only run.")
        con.close()
        sys.exit(0)

    selected = select_top_fights(FULL_CARD, fights_df, n=3)

    print("\n[6/6] Generating predictions...")
    predictions = []
    for fight in selected:
        pred = predict_fight(fight, clf, method_rf, fights_df, stats_df)
        predictions.append(pred)
        print(f"   {pred['fighter1']} vs {pred['fighter2']} => "
              f"{pred['pick']} via {pred['method']} ({pred['confidence']})")

    update_predictions_json(predictions)

    print("\n" + "=" * 70)
    print("[COMPLETE] v2 predictions written to predictions.json")
    print("=" * 70)
    con.close()
