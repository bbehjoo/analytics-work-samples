# =============================================================================
# WORK SAMPLE — from The Fight Algorithm (thefightalgorithm.com). SQL-heavy
# analytics sample (DuckDB).
#
# What this demonstrates:
#   - Complex analytical SQL over fight data: self-joins to pair combatants within
#     a bout, window functions, CTEs, and careful sample-size thresholds to keep
#     leaderboards honest (a defensible, documented methodology).
#   - Computes a defensive "chin" metric (knockdowns absorbed per fight) across
#     1,800+ fighters and exports leaderboards + distributions as JSON.
#
# Original code, unmodified except for this header. Runs against the publication's
# own DuckDB database; included here for review.
# =============================================================================

"""
Article 17: The Chin Index
Measures defensive chin durability via knockdowns ABSORBED per fight.

For each UFC fighter, sums the opposing fighter's `round_stats.knockdowns` across
all their bouts. This is the inverse of Article 6 (Knockout Artist) — same column,
opposite side of the strike.

Outputs JSON files prefixed `article17_` to website/public/data/.
"""
import io
import json
import sys
from pathlib import Path

import duckdb

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ufcstats.duckdb"
OUT_DIR = ROOT.parent / "website" / "public" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Min fights to qualify for leaderboards. 10 lifts out 7-fight noise like Hyun Gyu Lim.
LEADERBOARD_MIN_FIGHTS = 10
# Min fights to qualify for the full distribution (looser).
DISTRIBUTION_MIN_FIGHTS = 5


def write_json(name: str, payload):
    p = OUT_DIR / f"article17_{name}.json"
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {p.name}")


print("=" * 70)
print("ARTICLE 17: THE CHIN INDEX")
print("=" * 70)

con = duckdb.connect(str(DB_PATH), read_only=True)

# ============================================================================
# Fighter name lookup
# ============================================================================
print("\nBuilding fighter name lookup...")
name_rows = con.execute(
    """
    SELECT DISTINCT fighter1_url AS url, fighter1_name AS name FROM fight_details
    UNION
    SELECT DISTINCT fighter2_url AS url, fighter2_name AS name FROM fight_details
    """
).fetchall()
fighter_names = {url: name for url, name in name_rows if url and name}
print(f"   {len(fighter_names)} fighters mapped")

# ============================================================================
# Core: per-fighter knockdown ABSORBED counts + KO-loss counts
# ============================================================================
# For each fight a fighter participated in, the KDs they absorbed equal the sum
# of their opponent's row in round_stats. We use a window approach: for each
# (fight_id, fighter_url) row, sum knockdowns by the OTHER fighter in that fight.
print("\nComputing knockdowns-absorbed per fighter...")

chin_rows = con.execute(
    """
    WITH per_fighter_fight AS (
        -- One row per (fight, fighter) with KDs scored BY them
        SELECT
            fight_id,
            fighter_url,
            SUM(knockdowns) AS kd_scored,
            COUNT(*) AS rounds
        FROM round_stats
        GROUP BY fight_id, fighter_url
    ),
    paired AS (
        -- Join the two fighters of each fight, so absorbed = opponent's scored
        SELECT
            a.fighter_url,
            a.fight_id,
            b.kd_scored AS kd_absorbed,
            a.rounds AS rounds_fought
        FROM per_fighter_fight a
        JOIN per_fighter_fight b
          ON a.fight_id = b.fight_id
         AND a.fighter_url != b.fighter_url
    ),
    fight_outcome AS (
        SELECT
            fight_id,
            fighter1_url,
            fighter2_url,
            winner,
            method
        FROM fight_details
        WHERE winner IS NOT NULL
    ),
    loss_flag AS (
        -- 1 if this fighter LOST that fight by KO/TKO
        SELECT
            p.fighter_url,
            p.fight_id,
            p.kd_absorbed,
            p.rounds_fought,
            CASE
                WHEN fo.method = 'KO/TKO'
                 AND ((fo.winner = 'fighter1' AND fo.fighter2_url = p.fighter_url)
                   OR (fo.winner = 'fighter2' AND fo.fighter1_url = p.fighter_url))
                THEN 1 ELSE 0
            END AS lost_by_ko
        FROM paired p
        LEFT JOIN fight_outcome fo ON fo.fight_id = p.fight_id
    )
    SELECT
        fighter_url,
        COUNT(*) AS fights,
        SUM(rounds_fought) AS rounds,
        SUM(kd_absorbed) AS kd_absorbed,
        SUM(lost_by_ko) AS ko_losses
    FROM loss_flag
    GROUP BY fighter_url
    """
).fetchall()

# Build a name-resolved dict
chin = {}
for url, fights, rounds, kd_absorbed, ko_losses in chin_rows:
    if not url or not fights:
        continue
    chin[url] = {
        "fighter": fighter_names.get(url, "Unknown"),
        "fighterUrl": url,
        "fights": int(fights),
        "rounds": int(rounds or 0),
        "kdAbsorbed": int(kd_absorbed or 0),
        "koLosses": int(ko_losses or 0),
        "kdPerFight": round((kd_absorbed or 0) / fights, 3) if fights else 0.0,
        "kdPerRound": round((kd_absorbed or 0) / rounds, 4) if rounds else 0.0,
    }
print(f"   {len(chin)} fighters analyzed")

# Disambiguate duplicate names (e.g. multiple Tony Johnsons)
seen = {}
for entry in chin.values():
    n = entry["fighter"]
    if n in seen:
        seen[n] += 1
        entry["fighter"] = f"{n} ({seen[n]})"
    else:
        seen[n] = 1

# Spot-check the headline numbers
print("\nSpot-check:")
melendez = next((e for e in chin.values() if e["fighter"] == "Gilbert Melendez"), None)
if melendez:
    print(f"   Gilbert Melendez: {melendez['kdAbsorbed']} KDs, {melendez['fights']} fights, {melendez['koLosses']} KO losses")
horiguchi = next((e for e in chin.values() if e["fighter"] == "Kyoji Horiguchi"), None)
if horiguchi:
    print(f"   Kyoji Horiguchi: {horiguchi['kdAbsorbed']} KDs, {horiguchi['fights']} fights")
namajunas = next((e for e in chin.values() if e["fighter"] == "Rose Namajunas"), None)
if namajunas:
    print(f"   Rose Namajunas: {namajunas['kdAbsorbed']} KDs, {namajunas['fights']} fights, {namajunas['koLosses']} KO losses")

# ============================================================================
# 1. Distribution histogram (all eligible fighters)
# ============================================================================
print("\n[1/8] Chin Index Distribution")

distribution_pool = [e for e in chin.values() if e["fights"] >= DISTRIBUTION_MIN_FIGHTS]
print(f"   {len(distribution_pool)} fighters with >={DISTRIBUTION_MIN_FIGHTS} fights")

# Bucket by kdPerFight
BUCKETS = [
    ("0.00", 0.0, 0.001),
    ("0.01-0.10", 0.001, 0.1001),
    ("0.11-0.20", 0.1001, 0.2001),
    ("0.21-0.30", 0.2001, 0.3001),
    ("0.31-0.40", 0.3001, 0.4001),
    ("0.41-0.50", 0.4001, 0.5001),
    ("0.51-0.70", 0.5001, 0.7001),
    ("0.71+", 0.7001, 100.0),
]
bucket_counts = {b[0]: 0 for b in BUCKETS}
for e in distribution_pool:
    v = e["kdPerFight"]
    for label, lo, hi in BUCKETS:
        if lo <= v < hi:
            bucket_counts[label] += 1
            break

total = len(distribution_pool)
distribution = [
    {
        "bucket": label,
        "count": bucket_counts[label],
        "percentage": round(bucket_counts[label] / total * 100, 1) if total else 0,
    }
    for label, _, _ in BUCKETS
]
mean_kd = sum(e["kdPerFight"] for e in distribution_pool) / total if total else 0
sorted_kd = sorted(e["kdPerFight"] for e in distribution_pool)
median_kd = sorted_kd[len(sorted_kd) // 2] if sorted_kd else 0
write_json("chin_distribution", {
    "buckets": distribution,
    "totalFighters": total,
    "mean": round(mean_kd, 3),
    "median": round(median_kd, 3),
    "zeroKdCount": bucket_counts["0.00"],
    "zeroKdPct": round(bucket_counts["0.00"] / total * 100, 1) if total else 0,
})

# ============================================================================
# 2. Glass Jaws Leaderboard (top 15 highest KD/fight, min 10 fights)
# ============================================================================
print(f"\n[2/8] Glass Jaws (top 15 KD/fight, min {LEADERBOARD_MIN_FIGHTS} fights)")
qualified = [e for e in chin.values() if e["fights"] >= LEADERBOARD_MIN_FIGHTS]
glass_jaws = sorted(qualified, key=lambda e: (-e["kdPerFight"], -e["kdAbsorbed"]))[:15]
for e in glass_jaws:
    print(f"   {e['fighter']}: {e['kdPerFight']} KD/fight ({e['kdAbsorbed']} KDs / {e['fights']} fights, {e['koLosses']} KO losses)")
write_json("glass_jaws", glass_jaws)

# ============================================================================
# 3. Iron Chins Leaderboard (most fights with 0 KDs absorbed, min 10 fights)
# ============================================================================
print(f"\n[3/8] Iron Chins (0 KDs absorbed, min {LEADERBOARD_MIN_FIGHTS} fights)")
iron_chins = [e for e in qualified if e["kdAbsorbed"] == 0]
iron_chins.sort(key=lambda e: -e["fights"])
iron_chins = iron_chins[:15]
for e in iron_chins:
    print(f"   {e['fighter']}: {e['fights']} fights, 0 KDs absorbed, {e['koLosses']} KO losses")
write_json("iron_chins", iron_chins)

# ============================================================================
# 4. The Survivors (high KDs absorbed but zero KO losses, min 10 fights)
# ============================================================================
print(f"\n[4/8] The Survivors (high KD absorbed, 0 KO losses, min {LEADERBOARD_MIN_FIGHTS} fights)")
survivors = [e for e in qualified if e["kdAbsorbed"] >= 3 and e["koLosses"] == 0]
survivors.sort(key=lambda e: (-e["kdAbsorbed"], -e["kdPerFight"]))
survivors = survivors[:20]
for e in survivors:
    print(f"   {e['fighter']}: {e['kdAbsorbed']} KDs absorbed, 0 KO losses ({e['fights']} fights)")
write_json("survivors", survivors)

# ============================================================================
# 5. Weight class breakdown
# ============================================================================
print("\n[5/8] Weight class chin breakdown")
# Map fighters → weight class via their primary weight from fighters table
WEIGHT_CLASSES = [
    (115, 124, "Strawweight"),
    (125, 134, "Flyweight"),
    (135, 144, "Bantamweight"),
    (145, 154, "Featherweight"),
    (155, 169, "Lightweight"),
    (170, 184, "Welterweight"),
    (185, 204, "Middleweight"),
    (205, 224, "Light Heavyweight"),
    (225, 999, "Heavyweight"),
]


def parse_weight(w):
    if not w:
        return None
    import re
    m = re.search(r"(\d+)", w)
    return int(m.group(1)) if m else None


def weight_to_class(lb):
    if lb is None:
        return None
    for lo, hi, name in WEIGHT_CLASSES:
        if lo <= lb <= hi:
            return name
    return None


weight_rows = con.execute("SELECT fighter_url, weight FROM fighters WHERE weight IS NOT NULL").fetchall()
fighter_weight_class = {}
for url, weight in weight_rows:
    wc = weight_to_class(parse_weight(weight))
    if wc:
        fighter_weight_class[url] = wc

# Aggregate KDs absorbed and rounds per weight class for fighters with >=5 fights
from collections import defaultdict
wc_totals = defaultdict(lambda: {"fighters": 0, "kdAbsorbed": 0, "fights": 0, "rounds": 0, "koLosses": 0})
for url, entry in chin.items():
    if entry["fights"] < DISTRIBUTION_MIN_FIGHTS:
        continue
    wc = fighter_weight_class.get(url)
    if not wc:
        continue
    bucket = wc_totals[wc]
    bucket["fighters"] += 1
    bucket["kdAbsorbed"] += entry["kdAbsorbed"]
    bucket["fights"] += entry["fights"]
    bucket["rounds"] += entry["rounds"]
    bucket["koLosses"] += entry["koLosses"]

# Order: Strawweight → Heavyweight
DIVISION_ORDER = [name for _, _, name in WEIGHT_CLASSES]
weight_class_data = []
for div in DIVISION_ORDER:
    b = wc_totals.get(div)
    if not b or b["fights"] == 0:
        continue
    weight_class_data.append({
        "division": div,
        "fighters": b["fighters"],
        "kdAbsorbed": b["kdAbsorbed"],
        "fights": b["fights"],
        "rounds": b["rounds"],
        "kdPerFight": round(b["kdAbsorbed"] / b["fights"], 3),
        "kdPerRound": round(b["kdAbsorbed"] / b["rounds"], 4) if b["rounds"] else 0,
        "koLossPct": round(b["koLosses"] / b["fights"] * 100, 1),
    })
for d in weight_class_data:
    print(f"   {d['division']}: {d['kdPerFight']} KD/fight ({d['fighters']} fighters)")
write_json("weight_class", weight_class_data)

# ============================================================================
# 6. Does the chin age? KD-absorbed-per-fight by fighter age bucket
# ============================================================================
print("\n[6/8] Chin by age")
# Compute fighter age at time of each fight using dob + event_date.
# Use round_stats joined to events and fighters.
age_rows = con.execute(
    """
    WITH parsed_fighters AS (
        SELECT fighter_url, TRY_STRPTIME(dob, '%b %d, %Y') AS dob_dt
        FROM fighters
        WHERE dob IS NOT NULL AND dob != '--'
    ),
    age_per_fight AS (
        SELECT
            rs.fighter_url,
            rs.fight_id,
            DATE_DIFF('day', pf.dob_dt, e.event_date) / 365.25 AS age_at_fight
        FROM round_stats rs
        JOIN fights fi ON fi.fight_id = rs.fight_id
        JOIN events e ON e.event_id = fi.event_id
        JOIN parsed_fighters pf ON pf.fighter_url = rs.fighter_url
        WHERE pf.dob_dt IS NOT NULL AND e.event_date IS NOT NULL
        GROUP BY rs.fighter_url, rs.fight_id, pf.dob_dt, e.event_date
    ),
    kd_per_fight AS (
        -- Opponent's KD count = absorbed by this fighter
        SELECT
            a.fighter_url,
            a.fight_id,
            a.age_at_fight,
            SUM(b.knockdowns) AS kd_absorbed
        FROM age_per_fight a
        JOIN round_stats b
          ON b.fight_id = a.fight_id
         AND b.fighter_url != a.fighter_url
        GROUP BY a.fighter_url, a.fight_id, a.age_at_fight
    )
    SELECT age_at_fight, kd_absorbed FROM kd_per_fight
    WHERE age_at_fight BETWEEN 18 AND 50
    """
).fetchall()

# Bucket into age ranges
AGE_BUCKETS = [
    ("18-24", 18, 24.999),
    ("25-27", 25, 27.999),
    ("28-30", 28, 30.999),
    ("31-33", 31, 33.999),
    ("34-36", 34, 36.999),
    ("37-39", 37, 39.999),
    ("40+", 40, 100),
]
age_totals = {b[0]: {"fights": 0, "kdAbsorbed": 0} for b in AGE_BUCKETS}
for age, kd in age_rows:
    if age is None:
        continue
    for label, lo, hi in AGE_BUCKETS:
        if lo <= age <= hi:
            age_totals[label]["fights"] += 1
            age_totals[label]["kdAbsorbed"] += int(kd or 0)
            break

age_arc_data = []
for label, _, _ in AGE_BUCKETS:
    b = age_totals[label]
    if b["fights"] < 50:
        continue
    age_arc_data.append({
        "bucket": label,
        "fights": b["fights"],
        "kdAbsorbed": b["kdAbsorbed"],
        "kdPerFight": round(b["kdAbsorbed"] / b["fights"], 3),
    })
for d in age_arc_data:
    print(f"   age {d['bucket']}: {d['kdPerFight']} KD/fight (n={d['fights']})")
write_json("age_arc", age_arc_data)

# ============================================================================
# 7. KD-to-finish correlation (does absorbing KDs predict KO loss?)
# ============================================================================
print("\n[7/8] KD absorbed vs KO loss probability (scatter)")
# Use all qualified fighters (>=10 fights); KOLoss% = ko_losses / fights
scatter_data = []
for e in qualified:
    scatter_data.append({
        "fighter": e["fighter"],
        "fights": e["fights"],
        "kdAbsorbed": e["kdAbsorbed"],
        "kdPerFight": e["kdPerFight"],
        "koLosses": e["koLosses"],
        "koLossPct": round(e["koLosses"] / e["fights"] * 100, 1),
    })
# Sort by KD/fight desc for the front-end to slice if needed
scatter_data.sort(key=lambda x: -x["kdPerFight"])
print(f"   {len(scatter_data)} fighters in scatter")

# Compute correlation as a sanity check
import statistics
xs = [e["kdPerFight"] for e in scatter_data]
ys = [e["koLossPct"] for e in scatter_data]
if len(xs) > 2:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx, sy = statistics.stdev(xs), statistics.stdev(ys)
    if sx and sy:
        r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) * sx * sy) * (len(xs) / (len(xs) - 1))
        print(f"   Pearson r between kdPerFight and koLossPct: {r:.3f}")
write_json("kd_to_finish", scatter_data)

# ============================================================================
# 8. Active watchlist — fighters trending dangerous in the last ~3 years
# ============================================================================
print("\n[8/8] Active watchlist — fighters with rising chin risk")
# Active = had a UFC fight in 2024 or 2025. Compute their recent-only chin index
# (last 5 UFC fights) vs career, flag those whose recent rate >= 0.6.
watchlist_rows = con.execute(
    """
    WITH per_fighter_fight AS (
        SELECT
            rs.fight_id,
            rs.fighter_url,
            e.event_date,
            SUM(rs.knockdowns) AS kd_scored
        FROM round_stats rs
        JOIN fights fi ON fi.fight_id = rs.fight_id
        JOIN events e ON e.event_id = fi.event_id
        WHERE e.event_date IS NOT NULL
        GROUP BY rs.fight_id, rs.fighter_url, e.event_date
    ),
    paired AS (
        SELECT
            a.fighter_url,
            a.fight_id,
            a.event_date,
            b.kd_scored AS kd_absorbed
        FROM per_fighter_fight a
        JOIN per_fighter_fight b
          ON a.fight_id = b.fight_id
         AND a.fighter_url != b.fighter_url
    ),
    ranked AS (
        SELECT
            fighter_url,
            event_date,
            kd_absorbed,
            ROW_NUMBER() OVER (PARTITION BY fighter_url ORDER BY event_date DESC) AS rn
        FROM paired
    )
    SELECT
        fighter_url,
        MAX(event_date) AS last_fight,
        SUM(CASE WHEN rn <= 5 THEN kd_absorbed ELSE 0 END) AS recent_kd,
        COUNT(CASE WHEN rn <= 5 THEN 1 END) AS recent_fights
    FROM ranked
    GROUP BY fighter_url
    """
).fetchall()

watchlist = []
for url, last_fight, recent_kd, recent_fights in watchlist_rows:
    if not url or recent_fights is None or recent_fights < 3:
        continue
    if last_fight is None:
        continue
    # Active = fought in 2024 or 2025
    year = last_fight.year if hasattr(last_fight, "year") else int(str(last_fight)[:4])
    if year < 2024:
        continue
    entry = chin.get(url)
    if not entry:
        continue
    recent_per_fight = (recent_kd or 0) / recent_fights
    if recent_per_fight >= 0.6:  # flag threshold
        watchlist.append({
            "fighter": entry["fighter"],
            "lastFight": str(last_fight),
            "recentKd": int(recent_kd or 0),
            "recentFights": int(recent_fights),
            "recentKdPerFight": round(recent_per_fight, 2),
            "careerKdPerFight": entry["kdPerFight"],
            "careerFights": entry["fights"],
            "careerKoLosses": entry["koLosses"],
        })
watchlist.sort(key=lambda x: -x["recentKdPerFight"])
watchlist = watchlist[:12]
for w in watchlist:
    print(f"   {w['fighter']}: recent {w['recentKdPerFight']} KD/fight ({w['recentKd']}/{w['recentFights']}), last fight {w['lastFight']}")
write_json("active_watchlist", watchlist)

con.close()
print("\nDone.")
