/* =============================================================================
 * WORK SAMPLE - from The Fight Algorithm (thefightalgorithm.com). Procedural
 * TypeScript sample.
 *
 * What this demonstrates:
 *   - A self-contained Monte Carlo fight simulator: draws round-by-round outcomes
 *     from real statistical distributions (means/stds per fighter), accumulates a
 *     scorecard, and computes win probabilities over many simulated fights.
 *   - Strong typing (FighterProfile / RoundDistribution / scorecard types) and
 *     pure, testable functions powering an interactive tool on the website.
 *
 * Original code, unmodified except for this header.
 * =============================================================================
 */

/**
 * Fight Simulator Engine
 * ======================
 * Pure TypeScript simulation engine. Takes two fighter profiles and
 * produces a round-by-round simulated fight using real statistical
 * distributions from UFC data.
 */

// ── Types ──────────────────────────────────────────────────────────────────

export interface RoundDistribution {
  sig_str_landed: { mean: number; std: number };
  sig_str_attempted: { mean: number; std: number };
  sig_head_landed: { mean: number; std: number };
  sig_body_landed: { mean: number; std: number };
  sig_leg_landed: { mean: number; std: number };
  sig_distance_landed: { mean: number; std: number };
  sig_clinch_landed: { mean: number; std: number };
  sig_ground_landed: { mean: number; std: number };
  takedowns_landed: { mean: number; std: number };
  takedowns_attempted: { mean: number; std: number };
  knockdowns: { mean: number; std: number };
  submission_attempts: { mean: number; std: number };
  ctrl_seconds: { mean: number; std: number };
}

export interface FighterProfile {
  fights: number;
  sig_spm: number;
  sig_acc: number;
  sig_str_absorbed_spm: number;
  strike_differential_spm: number;
  td_per_fight: number;
  td_acc: number;
  sub_att_per_fight: number;
  kd_per_fight: number;
  ctrl_secs_per_fight: number;
  td_defense: number;
  dist_pct: number;
  clinch_pct: number;
  ground_pct: number;
  head_pct: number;
  body_pct: number;
  leg_pct: number;
  win_rate: number;
  finish_rate: number;
  ko_win_rate: number;
  sub_win_rate: number;
  dec_win_rate: number;
  recent_win_rate: number;
  recent_sig_spm: number;
  recent_sig_acc: number;
  recent_td_per_fight: number;
  recent_kd_per_fight: number;
  recent_ctrl_secs_per_fight: number;
  win_streak: number;
  loss_streak: number;
  log_fights: number;
  opp_accuracy_against: number;
  reversals_per_fight: number;
}

export interface SimFighter {
  name: string;
  height: string | null;
  reach: string | null;
  stance: string | null;
  weight: string | null;
  age: number | null;
  weightClass?: string | null;
  fights: number;
  profile: FighterProfile;
  roundStats: {
    r1: RoundDistribution | null;
    r2: RoundDistribution | null;
    r3plus: RoundDistribution | null;
  };
  finishRates: {
    ko_per_round: number[];
    sub_per_round: number[];
  } | null;
}

export interface SimRoundStats {
  sigStrikesLanded: number;
  sigStrikesAttempted: number;
  headLanded: number;
  bodyLanded: number;
  legLanded: number;
  takedownsLanded: number;
  takedownsAttempted: number;
  knockdowns: number;
  submissionAttempts: number;
  controlTime: number;
}

export interface SimRound {
  round: number;
  fighter1Stats: SimRoundStats;
  fighter2Stats: SimRoundStats;
  positionBreakdown: { distance: number; clinch: number; ground: number };
  events: FightEvent[];
}

export interface FightEvent {
  tick: number;
  type: 'knockdown' | 'takedown' | 'submission_attempt' | 'standup' | 'finish';
  fighter: string;
  description: string;
}

export interface Scorecard {
  judge: string;
  rounds: { fighter1: number; fighter2: number }[];
  total: { fighter1: number; fighter2: number };
}

export interface SimulatedFight {
  fighter1: string;
  fighter2: string;
  winner: string;
  loser: string;
  method: string;
  finishRound?: number;
  finishTime?: string;
  rounds: SimRound[];
  scorecards?: Scorecard[];
  summary: string;
}

export interface WeightClassMultiplier {
  ko_mult: number;
  sub_mult: number;
  ko_rate: number;
  sub_rate: number;
  fights: number;
}

export type ModelVersion = 'v2' | 'v2.1' | 'v2.2' | 'v2.3';

export interface GlobalAverages {
  r1: RoundDistribution;
  r2: RoundDistribution;
  r3plus: RoundDistribution;
  finish_rates: {
    ko_rate: number;
    sub_rate: number;
    dec_rate: number;
  };
  weight_class_multipliers?: Record<string, WeightClassMultiplier>;
  avg_sig_str_absorbed_spm?: number;
}

// ── PRNG (seeded) ──────────────────────────────────────────────────────────

class SeededRandom {
  private state: number;

  constructor(seed: number) {
    this.state = seed;
  }

  /** Returns a random float in [0, 1) */
  next(): number {
    this.state = (this.state * 1664525 + 1013904223) & 0xffffffff;
    return (this.state >>> 0) / 4294967296;
  }

  /** Normal distribution via Box-Muller */
  nextGaussian(mean: number, std: number): number {
    const u1 = this.next();
    const u2 = this.next();
    const z = Math.sqrt(-2.0 * Math.log(u1 + 0.0001)) * Math.cos(2.0 * Math.PI * u2);
    return mean + std * z;
  }

  /** Returns true with given probability */
  bernoulli(p: number): boolean {
    return this.next() < p;
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/** Parse reach string like '72"' or "72" to number, returns null if invalid */
function parseReach(reach: string | null): number | null {
  if (!reach) return null;
  const match = reach.replace(/"/g, '').match(/[\d.]+/);
  return match ? parseFloat(match[0]) : null;
}

/** Blend fighter stat with global average based on fight count (Bayesian shrinkage) */
function shrink(
  fighterDist: { mean: number; std: number } | undefined,
  globalDist: { mean: number; std: number } | undefined,
  fights: number,
): { mean: number; std: number } {
  const gMean = globalDist?.mean ?? 10;
  const gStd = globalDist?.std ?? 5;
  if (!fighterDist) return { mean: gMean, std: gStd };
  const weight = Math.min(fights, 15) / 15;
  return {
    mean: weight * fighterDist.mean + (1 - weight) * gMean,
    std: weight * fighterDist.std + (1 - weight) * gStd,
  };
}

/** Get the round distribution for a specific round number */
function getRoundDist(
  fighter: SimFighter,
  round: number,
  globalAvg: GlobalAverages,
): RoundDistribution {
  const roundKey = round === 1 ? 'r1' : round === 2 ? 'r2' : 'r3plus';
  const globalKey = roundKey;
  const fighterDist = fighter.roundStats?.[roundKey];
  const globalDist = globalAvg[globalKey];
  const fights = fighter.fights;

  const cols: (keyof RoundDistribution)[] = [
    'sig_str_landed', 'sig_str_attempted',
    'sig_head_landed', 'sig_body_landed', 'sig_leg_landed',
    'sig_distance_landed', 'sig_clinch_landed', 'sig_ground_landed',
    'takedowns_landed', 'takedowns_attempted',
    'knockdowns', 'submission_attempts', 'ctrl_seconds',
  ];

  const result: Record<string, { mean: number; std: number }> = {};
  for (const col of cols) {
    result[col] = shrink(
      fighterDist?.[col],
      globalDist?.[col],
      fights,
    );
  }
  return result as unknown as RoundDistribution;
}

/** Age threshold at which chin deterioration and fatigue kick in, by weight class.
 *  Heavier fighters' chins hold up longer; lighter fighters lose speed earlier. */
function getAgeThresholds(weightClass: string | null | undefined): { chin: number; fatigue: number } {
  const wc = (weightClass || '').toLowerCase();
  if (wc.includes('heavyweight') && !wc.includes('light')) return { chin: 39, fatigue: 37 };
  if (wc.includes('light heavyweight'))                     return { chin: 38, fatigue: 36 };
  if (wc.includes('middleweight') && !wc.includes('women')) return { chin: 37, fatigue: 35 };
  if (wc.includes('welterweight'))                          return { chin: 36, fatigue: 35 };
  if (wc.includes('lightweight'))                           return { chin: 35, fatigue: 34 };
  if (wc.includes('featherweight'))                         return { chin: 35, fatigue: 34 };
  if (wc.includes('bantamweight') && !wc.includes('women')) return { chin: 34, fatigue: 33 };
  if (wc.includes('flyweight') && !wc.includes('women'))    return { chin: 34, fatigue: 33 };
  // Women's divisions — roughly same as men's lighter weights
  if (wc.includes('women'))                                 return { chin: 35, fatigue: 34 };
  return { chin: 36, fatigue: 34 }; // default
}

// ── Position State Machine ─────────────────────────────────────────────────

type Position = 'distance' | 'clinch' | 'ground';

const TICKS_PER_ROUND = 20; // 15 seconds per tick, 20 ticks = 5 min

// ── Core Simulation ────────────────────────────────────────────────────────

export function simulateFight(
  fighter1: SimFighter,
  fighter2: SimFighter,
  globalAvg: GlobalAverages,
  options: { numRounds?: 3 | 5; seed?: number; modelVersion?: ModelVersion } = {},
): SimulatedFight {
  const numRounds = options.numRounds ?? 3;
  const seed = options.seed ?? Math.floor(Math.random() * 2147483647);
  const modelVersion = options.modelVersion ?? 'v2.3';
  const rng = new SeededRandom(seed);

  const f1Name = fighter1.name;
  const f2Name = fighter2.name;
  const p1 = fighter1.profile;
  const p2 = fighter2.profile;

  // ── v2.2+: Recent form blending (blend career and recent stats at 60/40) ──
  const useRecentBlend = modelVersion === 'v2.2' || modelVersion === 'v2.3';
  const eff1 = useRecentBlend ? {
    sig_spm: p1.sig_spm * 0.6 + p1.recent_sig_spm * 0.4,
    sig_acc: p1.sig_acc * 0.6 + p1.recent_sig_acc * 0.4,
    td_per_fight: p1.td_per_fight * 0.6 + p1.recent_td_per_fight * 0.4,
    kd_per_fight: p1.kd_per_fight * 0.6 + p1.recent_kd_per_fight * 0.4,
    ctrl_secs_per_fight: p1.ctrl_secs_per_fight * 0.6 + p1.recent_ctrl_secs_per_fight * 0.4,
  } : {
    sig_spm: p1.sig_spm,
    sig_acc: p1.sig_acc,
    td_per_fight: p1.td_per_fight,
    kd_per_fight: p1.kd_per_fight,
    ctrl_secs_per_fight: p1.ctrl_secs_per_fight,
  };
  const eff2 = useRecentBlend ? {
    sig_spm: p2.sig_spm * 0.6 + p2.recent_sig_spm * 0.4,
    sig_acc: p2.sig_acc * 0.6 + p2.recent_sig_acc * 0.4,
    td_per_fight: p2.td_per_fight * 0.6 + p2.recent_td_per_fight * 0.4,
    kd_per_fight: p2.kd_per_fight * 0.6 + p2.recent_kd_per_fight * 0.4,
    ctrl_secs_per_fight: p2.ctrl_secs_per_fight * 0.6 + p2.recent_ctrl_secs_per_fight * 0.4,
  } : {
    sig_spm: p2.sig_spm,
    sig_acc: p2.sig_acc,
    td_per_fight: p2.td_per_fight,
    kd_per_fight: p2.kd_per_fight,
    ctrl_secs_per_fight: p2.ctrl_secs_per_fight,
  };

  // Pre-compute matchup modifiers
  const reach1 = parseReach(fighter1.reach);
  const reach2 = parseReach(fighter2.reach);
  const reachDiff = (reach1 && reach2) ? reach1 - reach2 : 0;

  // Reach advantage: boost distance striking for the longer fighter
  const f1ReachMod = reachDiff > 3 ? 1.08 : reachDiff > 0 ? 1.03 : reachDiff < -3 ? 0.95 : reachDiff < 0 ? 0.97 : 1.0;
  const f2ReachMod = reachDiff < -3 ? 1.08 : reachDiff < 0 ? 1.03 : reachDiff > 3 ? 0.95 : reachDiff > 0 ? 0.97 : 1.0;

  // ── v2.2+: Stance matchup modifiers ──
  let f1StanceMod = 1.0;
  let f2StanceMod = 1.0;
  if (modelVersion === 'v2.2' || modelVersion === 'v2.3') {
    const s1 = (fighter1.stance || '').toLowerCase();
    const s2 = (fighter2.stance || '').toLowerCase();
    if (s1 === 'switch') {
      f1StanceMod = 1.02;
      f2StanceMod = 0.98;
    } else if (s2 === 'switch') {
      f2StanceMod = 1.02;
      f1StanceMod = 0.98;
    } else if ((s1 === 'southpaw') !== (s2 === 'southpaw') && s1 && s2) {
      // Open stance matchup: southpaw gets slight edge
      if (s1 === 'southpaw') f1StanceMod = 1.03;
      else f2StanceMod = 1.03;
    }
  }

  // Skill edge: dominant fighters impose their game plan more effectively
  let f1Skill: number;
  let f2Skill: number;
  if (modelVersion === 'v2') {
    // v2: original formula
    f1Skill = p1.win_rate * 0.7 + p1.recent_win_rate * 0.3;
    f2Skill = p2.win_rate * 0.7 + p2.recent_win_rate * 0.3;
  } else {
    // v2.1+: blend in strike differential for intensity-of-dominance signal
    f1Skill = p1.win_rate * 0.5 + p1.recent_win_rate * 0.2
      + clamp(p1.strike_differential_spm / 5, -0.3, 0.3) * 0.3;
    f2Skill = p2.win_rate * 0.5 + p2.recent_win_rate * 0.2
      + clamp(p2.strike_differential_spm / 5, -0.3, 0.3) * 0.3;
  }
  const f1Edge = clamp(1 + (f1Skill - f2Skill) * 2.5, 0.6, 1.8);
  const f2Edge = clamp(1 + (f2Skill - f1Skill) * 2.5, 0.6, 1.8);

  // ── v2.1+: Weight class finish multipliers ──
  let wcKoMult = 1.0;
  let wcSubMult = 1.0;
  if (modelVersion !== 'v2') {
    const wc = fighter1.weightClass || fighter2.weightClass;
    if (wc && globalAvg.weight_class_multipliers?.[wc]) {
      const m = globalAvg.weight_class_multipliers[wc];
      wcKoMult = m.ko_mult;
      wcSubMult = m.sub_mult;
    }
  }

  // ── v2.1+: Absorption defense modifier (fighters with low absorption take less damage) ──
  let f1AbsorbMod = 1.0; // modifier on damage TAKEN by f1
  let f2AbsorbMod = 1.0; // modifier on damage TAKEN by f2
  if (modelVersion !== 'v2') {
    const globalAbsorb = globalAvg.avg_sig_str_absorbed_spm ?? 3.55;
    // Low absorption → less damage taken; high absorption → more damage taken
    f1AbsorbMod = clamp(1.0 + (p1.sig_str_absorbed_spm - globalAbsorb) * 0.08, 0.7, 1.3);
    f2AbsorbMod = clamp(1.0 + (p2.sig_str_absorbed_spm - globalAbsorb) * 0.08, 0.7, 1.3);
  }

  // ── v2.3: Strike defense rate modifier ──
  let f1DefenseAccMod = 1.0; // opponent accuracy modifier when striking at f1
  let f2DefenseAccMod = 1.0;
  if (modelVersion === 'v2.3') {
    // opp_accuracy_against: what % of strikes thrown at this fighter land
    // Global average is roughly ~0.44. Lower = better defense.
    const globalOppAcc = 0.44;
    f1DefenseAccMod = clamp(p1.opp_accuracy_against / globalOppAcc, 0.85, 1.15);
    f2DefenseAccMod = clamp(p2.opp_accuracy_against / globalOppAcc, 0.85, 1.15);
  }

  // Damage meters (0-100)
  let f1Damage = 0;
  let f2Damage = 0;
  let f1DamageThreshold = 70 + rng.next() * 25; // 70-95
  let f2DamageThreshold = 70 + rng.next() * 25;

  // ── v2.2+: Age-based chin deterioration (weight-class-aware) ──
  if (modelVersion === 'v2.2' || modelVersion === 'v2.3') {
    const f1Age = fighter1.age ?? 30;
    const f2Age = fighter2.age ?? 30;
    const f1AgeThresh = getAgeThresholds(fighter1.weightClass);
    const f2AgeThresh = getAgeThresholds(fighter2.weightClass);
    if (f1Age > f1AgeThresh.chin) f1DamageThreshold -= Math.min((f1Age - f1AgeThresh.chin) * 3, 15);
    if (f2Age > f2AgeThresh.chin) f2DamageThreshold -= Math.min((f2Age - f2AgeThresh.chin) * 3, 15);
  }

  const rounds: SimRound[] = [];
  let finishRound: number | undefined;
  let finishTime: string | undefined;
  let finishMethod: string | undefined;
  let finishWinner: string | undefined;

  for (let r = 1; r <= numRounds; r++) {
    if (finishRound) break;

    const f1Dist = getRoundDist(fighter1, r, globalAvg);
    const f2Dist = getRoundDist(fighter2, r, globalAvg);

    const f1RoundStats: SimRoundStats = {
      sigStrikesLanded: 0, sigStrikesAttempted: 0,
      headLanded: 0, bodyLanded: 0, legLanded: 0,
      takedownsLanded: 0, takedownsAttempted: 0,
      knockdowns: 0, submissionAttempts: 0, controlTime: 0,
    };
    const f2RoundStats: SimRoundStats = {
      sigStrikesLanded: 0, sigStrikesAttempted: 0,
      headLanded: 0, bodyLanded: 0, legLanded: 0,
      takedownsLanded: 0, takedownsAttempted: 0,
      knockdowns: 0, submissionAttempts: 0, controlTime: 0,
    };

    const posBreakdown = { distance: 0, clinch: 0, ground: 0 };
    const events: FightEvent[] = [];
    let position: Position = 'distance';
    let groundTopFighter: 1 | 2 = 1; // who's on top

    for (let tick = 0; tick < TICKS_PER_ROUND; tick++) {
      if (finishRound) break;

      const tickSeconds = 15;

      // ── Position Transitions ──

      // v2.1+: Pre-compute style mismatch & grappling modifiers
      // Fix 1: Style mismatch — grapplers shoot more on pure strikers
      // Fix 2: Skill edge amplifies position seeking (dominant fighters impose their game)
      // Fix 3: TD defense gap — big gap between attacker quality and defender quality
      let f1TdBoost = 1.0;
      let f2TdBoost = 1.0;
      let f1TdSuccessBoost = 1.0;
      let f2TdSuccessBoost = 1.0;
      if (modelVersion !== 'v2') {
        // Fix 1: Style mismatch — when a grappler faces a pure striker, they shoot more
        // Detected by: attacker has high td_per_fight, defender has low ground_pct
        const f1GrapplerVsStriker = eff1.td_per_fight > 1.5 && p2.ground_pct < 0.15;
        const f2GrapplerVsStriker = eff2.td_per_fight > 1.5 && p1.ground_pct < 0.15;
        const f1StyleMismatch = f1GrapplerVsStriker ? clamp(1.0 + (eff1.td_per_fight - 1.5) * 0.3, 1.0, 2.0) : 1.0;
        const f2StyleMismatch = f2GrapplerVsStriker ? clamp(1.0 + (eff2.td_per_fight - 1.5) * 0.3, 1.0, 2.0) : 1.0;

        // Fix 2: Skill edge amplifies ground seeking — dominant fighters impose their game
        const f1SkillGroundSeek = f1Edge > 1.1 ? clamp(f1Edge * 0.8, 1.0, 1.5) : 1.0;
        const f2SkillGroundSeek = f2Edge > 1.1 ? clamp(f2Edge * 0.8, 1.0, 1.5) : 1.0;

        // Position preference (existing)
        const f1PosSeek = clamp(p1.ground_pct / 0.15, 0.5, 2.0);
        const f2PosSeek = clamp(p2.ground_pct / 0.15, 0.5, 2.0);

        f1TdBoost = f1StyleMismatch * f1SkillGroundSeek * f1PosSeek;
        f2TdBoost = f2StyleMismatch * f2SkillGroundSeek * f2PosSeek;

        // Fix 3: TD defense gap exploitation — when there's a big gap, success rate jumps
        // E.g., Jones (td_acc 0.47) vs Pereira (td_def 0.79) → gap = 0.47 - (1-0.79) = 0.26
        // High gap means attacker's accuracy far exceeds what defender can stuff
        const f1TdGap = p1.td_acc - (1 - p2.td_defense);
        const f2TdGap = p2.td_acc - (1 - p1.td_defense);
        f1TdSuccessBoost = f1TdGap > 0.1 ? clamp(1.0 + f1TdGap * 0.8, 1.0, 1.4) : 1.0;
        f2TdSuccessBoost = f2TdGap > 0.1 ? clamp(1.0 + f2TdGap * 0.8, 1.0, 1.4) : 1.0;
      }

      if (position === 'distance') {
        // Clinch entry probability
        const clinchDesire = (p1.clinch_pct + p2.clinch_pct) / 2;
        const clinchProb = clinchDesire * 0.5; // ~5-8% per tick based on clinch tendency
        if (rng.bernoulli(clinchProb)) {
          position = 'clinch';
        }

        // Takedown attempt from distance
        const f1TdAttemptProb = eff1.td_per_fight * 0.04 * f1Edge * f1TdBoost;
        const f2TdAttemptProb = eff2.td_per_fight * 0.04 * f2Edge * f2TdBoost;

        if (rng.bernoulli(f1TdAttemptProb)) {
          f1RoundStats.takedownsAttempted++;
          const success = rng.bernoulli(
            Math.pow(p1.td_acc, 0.4) * (1 - p2.td_defense * 0.6) * clamp(f1Edge, 0.8, 1.3) * f1TdSuccessBoost
          );
          if (success) {
            f1RoundStats.takedownsLanded++;
            position = 'ground';
            groundTopFighter = 1;
            events.push({ tick, type: 'takedown', fighter: f1Name, description: `${f1Name} completes a takedown` });
          }
        } else if (rng.bernoulli(f2TdAttemptProb)) {
          f2RoundStats.takedownsAttempted++;
          const success = rng.bernoulli(
            Math.pow(p2.td_acc, 0.4) * (1 - p1.td_defense * 0.6) * clamp(f2Edge, 0.8, 1.3) * f2TdSuccessBoost
          );
          if (success) {
            f2RoundStats.takedownsLanded++;
            position = 'ground';
            groundTopFighter = 2;
            events.push({ tick, type: 'takedown', fighter: f2Name, description: `${f2Name} completes a takedown` });
          }
        }
      } else if (position === 'clinch') {
        // Break from clinch back to distance
        // v2.1+: distance fighters break the clinch faster
        const clinchBreakBase = 0.25;
        const distBoost = modelVersion !== 'v2'
          ? clamp((p1.dist_pct + p2.dist_pct) / 2 / 0.6, 0.8, 1.4)
          : 1.0;
        if (rng.bernoulli(clinchBreakBase * distBoost)) {
          position = 'distance';
        }
        // Takedown from clinch (higher probability)
        const f1TdProb = eff1.td_per_fight * 0.08 * f1Edge * f1TdBoost;
        const f2TdProb = eff2.td_per_fight * 0.08 * f2Edge * f2TdBoost;
        if (rng.bernoulli(f1TdProb)) {
          f1RoundStats.takedownsAttempted++;
          const success = rng.bernoulli(
            Math.pow(p1.td_acc, 0.4) * (1 - p2.td_defense * 0.5) * clamp(f1Edge, 0.8, 1.3) * f1TdSuccessBoost
          );
          if (success) {
            f1RoundStats.takedownsLanded++;
            position = 'ground';
            groundTopFighter = 1;
            events.push({ tick, type: 'takedown', fighter: f1Name, description: `${f1Name} gets the takedown from the clinch` });
          }
        } else if (rng.bernoulli(f2TdProb)) {
          f2RoundStats.takedownsAttempted++;
          const success = rng.bernoulli(
            Math.pow(p2.td_acc, 0.4) * (1 - p1.td_defense * 0.5) * clamp(f2Edge, 0.8, 1.3) * f2TdSuccessBoost
          );
          if (success) {
            f2RoundStats.takedownsLanded++;
            position = 'ground';
            groundTopFighter = 2;
            events.push({ tick, type: 'takedown', fighter: f2Name, description: `${f2Name} gets the takedown from the clinch` });
          }
        }
      } else if (position === 'ground') {
        // Stand-up probability — skill edge makes elite grapplers harder to escape
        const topProfile = groundTopFighter === 1 ? p1 : p2;
        const bottomProfile = groundTopFighter === 1 ? p2 : p1;
        const topEdge = groundTopFighter === 1 ? f1Edge : f2Edge;
        const topEffCtrl = groundTopFighter === 1 ? eff1.ctrl_secs_per_fight : eff2.ctrl_secs_per_fight;
        const baseStandup = Math.max(0.08, 0.20 - topEffCtrl * 0.0005);
        // v2.1+: distance fighters escape ground faster
        const distEscapeBoost = modelVersion !== 'v2'
          ? clamp(bottomProfile.dist_pct / 0.6, 0.8, 1.4)
          : 1.0;
        // v2.3: reversals boost standup probability
        const reversalBoost = modelVersion === 'v2.3'
          ? 1.0 + clamp(bottomProfile.reversals_per_fight * 0.5, 0, 0.3)
          : 1.0;
        const standupProb = (baseStandup * distEscapeBoost * reversalBoost) / topEdge;
        if (rng.bernoulli(standupProb)) {
          position = 'distance';
          const bottomName = groundTopFighter === 1 ? f2Name : f1Name;
          events.push({ tick, type: 'standup', fighter: bottomName, description: `${bottomName} gets back to the feet` });
        }

        // Control time for top fighter
        const topStats = groundTopFighter === 1 ? f1RoundStats : f2RoundStats;
        topStats.controlTime += tickSeconds;
      }

      posBreakdown[position] += tickSeconds;

      // ── Striking per tick ──
      // Scale round-level means to per-tick
      // v2.2+: age-based late-round fatigue (weight-class-aware threshold)
      let f1AgeFatigue = 1.0;
      let f2AgeFatigue = 1.0;
      if ((modelVersion === 'v2.2' || modelVersion === 'v2.3') && r >= 3) {
        const f1Age = fighter1.age ?? 30;
        const f2Age = fighter2.age ?? 30;
        const f1FatThresh = getAgeThresholds(fighter1.weightClass).fatigue;
        const f2FatThresh = getAgeThresholds(fighter2.weightClass).fatigue;
        if (f1Age > f1FatThresh) f1AgeFatigue = clamp(1 - (f1Age - f1FatThresh) * 0.02, 0.85, 1.0);
        if (f2Age > f2FatThresh) f2AgeFatigue = clamp(1 - (f2Age - f2FatThresh) * 0.02, 0.85, 1.0);
      }
      const f1PerTick = f1Dist.sig_str_landed.mean / TICKS_PER_ROUND * f1AgeFatigue;
      const f2PerTick = f2Dist.sig_str_landed.mean / TICKS_PER_ROUND * f2AgeFatigue;
      const f1StdTick = f1Dist.sig_str_landed.std / Math.sqrt(TICKS_PER_ROUND);
      const f2StdTick = f2Dist.sig_str_landed.std / Math.sqrt(TICKS_PER_ROUND);

      let f1Strikes = 0;
      let f2Strikes = 0;

      if (position === 'distance') {
        // Full striking at distance, modified by reach and stance
        // v2.3: opponent defense accuracy modifier reduces landing rate
        const f1DistMod = f1ReachMod * f1StanceMod * f2DefenseAccMod;
        const f2DistMod = f2ReachMod * f2StanceMod * f1DefenseAccMod;
        f1Strikes = Math.round(clamp(rng.nextGaussian(f1PerTick * f1DistMod, f1StdTick), 0, 20));
        f2Strikes = Math.round(clamp(rng.nextGaussian(f2PerTick * f2DistMod, f2StdTick), 0, 20));
      } else if (position === 'clinch') {
        // Reduced striking in clinch
        const clinchScale = 0.4;
        f1Strikes = Math.round(clamp(rng.nextGaussian(f1PerTick * clinchScale, f1StdTick * 0.5), 0, 10));
        f2Strikes = Math.round(clamp(rng.nextGaussian(f2PerTick * clinchScale, f2StdTick * 0.5), 0, 10));
      } else {
        // Ground: top fighter has advantage
        const topScale = 0.5;
        const bottomScale = 0.08;
        if (groundTopFighter === 1) {
          f1Strikes = Math.round(clamp(rng.nextGaussian(f1PerTick * topScale, f1StdTick * 0.5), 0, 12));
          f2Strikes = Math.round(clamp(rng.nextGaussian(f2PerTick * bottomScale, f2StdTick * 0.3), 0, 5));
        } else {
          f2Strikes = Math.round(clamp(rng.nextGaussian(f2PerTick * topScale, f2StdTick * 0.5), 0, 12));
          f1Strikes = Math.round(clamp(rng.nextGaussian(f1PerTick * bottomScale, f1StdTick * 0.3), 0, 5));
        }
      }

      // Accuracy adjustment: attempted = landed / accuracy
      const f1EffAcc = eff1.sig_acc;
      const f2EffAcc = eff2.sig_acc;
      const f1Attempted = f1EffAcc > 0 ? Math.round(f1Strikes / f1EffAcc) : f1Strikes * 2;
      const f2Attempted = f2EffAcc > 0 ? Math.round(f2Strikes / f2EffAcc) : f2Strikes * 2;

      f1RoundStats.sigStrikesLanded += f1Strikes;
      f1RoundStats.sigStrikesAttempted += f1Attempted;
      f2RoundStats.sigStrikesLanded += f2Strikes;
      f2RoundStats.sigStrikesAttempted += f2Attempted;

      // Distribute to targets (head/body/leg)
      for (let i = 0; i < f1Strikes; i++) {
        const roll = rng.next();
        if (roll < p1.head_pct) f1RoundStats.headLanded++;
        else if (roll < p1.head_pct + p1.body_pct) f1RoundStats.bodyLanded++;
        else f1RoundStats.legLanded++;
      }
      for (let i = 0; i < f2Strikes; i++) {
        const roll = rng.next();
        if (roll < p2.head_pct) f2RoundStats.headLanded++;
        else if (roll < p2.head_pct + p2.body_pct) f2RoundStats.bodyLanded++;
        else f2RoundStats.legLanded++;
      }

      // ── Damage accumulation ──
      // Scale by fighter's KO power: head strikes hurt more from power punchers
      // v2.1+: weight class multiplier on damage, absorption defense on damage taken
      const f1HeadDmg = (0.4 + p1.ko_win_rate * 0.8) * wcKoMult;
      const f2HeadDmg = (0.4 + p2.ko_win_rate * 0.8) * wcKoMult;
      const f1RawDmg = f1RoundStats.headLanded > 0 ? f1Strikes * f1HeadDmg : f1Strikes * 0.08;
      const f2RawDmg = f2RoundStats.headLanded > 0 ? f2Strikes * f2HeadDmg : f2Strikes * 0.08;
      f2Damage += f1RawDmg * f2AbsorbMod; // f2 takes damage from f1's strikes, scaled by f2's absorption
      f1Damage += f2RawDmg * f1AbsorbMod;

      // ── Knockdown check ──
      if (f1Strikes > 0 && position !== 'ground') {
        const headStrikes = Math.round(f1Strikes * p1.head_pct);
        // KD probability = real knockdown rate / estimated head strikes per fight
        const f1HeadPerFight = Math.max(eff1.sig_spm * 15 * p1.head_pct, 1);
        const f1KdProb = clamp(eff1.kd_per_fight / f1HeadPerFight, 0.002, 0.06);
        for (let s = 0; s < headStrikes; s++) {
          if (rng.bernoulli(f1KdProb)) {
            f1RoundStats.knockdowns++;
            f2Damage += 12 * f2AbsorbMod;
            events.push({ tick, type: 'knockdown', fighter: f1Name, description: `${f1Name} drops ${f2Name}!` });

            // KO check on knockdown — weighted by finish rate + KO rate
            // v2.1+: weight class KO multiplier
            const koProb = clamp(
              0.12 * (1 + p1.ko_win_rate + p1.finish_rate) * (1 + f2Damage / 120) * wcKoMult,
              0.08, 0.40,
            );
            if (rng.bernoulli(koProb)) {
              const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
              const min = Math.floor(finishSec / 60);
              const sec = finishSec % 60;
              finishRound = r;
              finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
              finishMethod = `KO/TKO Round ${r}`;
              finishWinner = f1Name;
              events.push({ tick, type: 'finish', fighter: f1Name, description: `${f1Name} finishes ${f2Name} with strikes! TKO at ${finishTime} of Round ${r}.` });
              break;
            }
            break; // Only one KD per tick
          }
        }
      }

      if (!finishRound && f2Strikes > 0 && position !== 'ground') {
        const headStrikes = Math.round(f2Strikes * p2.head_pct);
        const f2HeadPerFight = Math.max(eff2.sig_spm * 15 * p2.head_pct, 1);
        const f2KdProb = clamp(eff2.kd_per_fight / f2HeadPerFight, 0.002, 0.06);
        for (let s = 0; s < headStrikes; s++) {
          if (rng.bernoulli(f2KdProb)) {
            f2RoundStats.knockdowns++;
            f1Damage += 12 * f1AbsorbMod;
            events.push({ tick, type: 'knockdown', fighter: f2Name, description: `${f2Name} drops ${f1Name}!` });

            const koProb = clamp(
              0.12 * (1 + p2.ko_win_rate + p2.finish_rate) * (1 + f1Damage / 120) * wcKoMult,
              0.08, 0.40,
            );
            if (rng.bernoulli(koProb)) {
              const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
              const min = Math.floor(finishSec / 60);
              const sec = finishSec % 60;
              finishRound = r;
              finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
              finishMethod = `KO/TKO Round ${r}`;
              finishWinner = f2Name;
              events.push({ tick, type: 'finish', fighter: f2Name, description: `${f2Name} finishes ${f1Name} with strikes! TKO at ${finishTime} of Round ${r}.` });
              break;
            }
            break;
          }
        }
      }

      // ── Submission check (ground only) ──
      if (!finishRound && position === 'ground') {
        const bottomFighter = groundTopFighter === 1 ? 2 : 1;
        const topProfile = groundTopFighter === 1 ? p1 : p2;
        const bottomProfile = groundTopFighter === 1 ? p2 : p1;
        const topStats = groundTopFighter === 1 ? f1RoundStats : f2RoundStats;
        const bottomStats = groundTopFighter === 1 ? f2RoundStats : f1RoundStats;

        // Top fighter submission attempts
        const topSubProb = topProfile.sub_att_per_fight * 0.03;
        if (rng.bernoulli(topSubProb)) {
          topStats.submissionAttempts++;
          events.push({
            tick, type: 'submission_attempt',
            fighter: groundTopFighter === 1 ? f1Name : f2Name,
            description: `${groundTopFighter === 1 ? f1Name : f2Name} looks for a submission`,
          });

          // Sub success — v2.1+: weight class sub multiplier
          const subConvRate = topProfile.sub_win_rate > 0 && topProfile.sub_att_per_fight > 0
            ? topProfile.sub_win_rate / topProfile.sub_att_per_fight
            : 0.05;
          const controlBonus = Math.min(topStats.controlTime / 120, 0.5);
          const successProb = clamp(subConvRate * (1 + controlBonus) * wcSubMult, 0, 0.35);

          if (rng.bernoulli(successProb)) {
            const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
            const min = Math.floor(finishSec / 60);
            const sec = finishSec % 60;
            finishRound = r;
            finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
            finishMethod = `Submission Round ${r}`;
            finishWinner = groundTopFighter === 1 ? f1Name : f2Name;
            events.push({
              tick, type: 'finish',
              fighter: finishWinner,
              description: `${finishWinner} locks in the submission! Tap at ${finishTime} of Round ${r}.`,
            });
          }
        }

        // Bottom fighter sub attempt (less likely but possible — guard subs)
        const bottomSubProb = bottomProfile.sub_att_per_fight * 0.015;
        if (!finishRound && rng.bernoulli(bottomSubProb)) {
          bottomStats.submissionAttempts++;
          const bottomSubConvRate = bottomProfile.sub_win_rate > 0 && bottomProfile.sub_att_per_fight > 0
            ? bottomProfile.sub_win_rate / bottomProfile.sub_att_per_fight
            : 0.03;
          if (rng.bernoulli(clamp(bottomSubConvRate * 0.6 * wcSubMult, 0, 0.2))) {
            const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
            const min = Math.floor(finishSec / 60);
            const sec = finishSec % 60;
            finishRound = r;
            finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
            finishMethod = `Submission Round ${r}`;
            finishWinner = bottomFighter === 1 ? f1Name : f2Name;
            events.push({
              tick, type: 'finish',
              fighter: finishWinner,
              description: `${finishWinner} catches a submission off the back! Tap at ${finishTime} of Round ${r}.`,
            });
          }
        }
      }

      // ── Accumulation TKO check (high damage, lots of strikes absorbed) ──
      if (!finishRound && tick > 5) {
        if (f2Damage > f2DamageThreshold && f1RoundStats.sigStrikesLanded > 8) {
          if (rng.bernoulli(0.08)) {
            const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
            const min = Math.floor(finishSec / 60);
            const sec = finishSec % 60;
            finishRound = r;
            finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
            finishMethod = `KO/TKO Round ${r}`;
            finishWinner = f1Name;
            events.push({ tick, type: 'finish', fighter: f1Name, description: `Referee stoppage! ${f1Name} wins by TKO at ${finishTime} of Round ${r}.` });
          }
        }
        if (!finishRound && f1Damage > f1DamageThreshold && f2RoundStats.sigStrikesLanded > 8) {
          if (rng.bernoulli(0.08)) {
            const finishSec = tick * 15 + Math.floor(rng.next() * 14) + 1;
            const min = Math.floor(finishSec / 60);
            const sec = finishSec % 60;
            finishRound = r;
            finishTime = `${min}:${sec.toString().padStart(2, '0')}`;
            finishMethod = `KO/TKO Round ${r}`;
            finishWinner = f2Name;
            events.push({ tick, type: 'finish', fighter: f2Name, description: `Referee stoppage! ${f2Name} wins by TKO at ${finishTime} of Round ${r}.` });
          }
        }
      }
    } // end tick loop

    rounds.push({
      round: r,
      fighter1Stats: f1RoundStats,
      fighter2Stats: f2RoundStats,
      positionBreakdown: posBreakdown,
      events,
    });
  } // end round loop

  // ── Decision Scoring ──
  let scorecards: Scorecard[] | undefined;
  if (!finishRound) {
    scorecards = scoreDecision(rounds, f1Name, f2Name, rng);
    const total1 = scorecards.reduce((sum, sc) => sum + sc.total.fighter1, 0);
    const total2 = scorecards.reduce((sum, sc) => sum + sc.total.fighter2, 0);

    const wins1 = scorecards.filter(sc => sc.total.fighter1 > sc.total.fighter2).length;
    const wins2 = scorecards.filter(sc => sc.total.fighter2 > sc.total.fighter1).length;

    if (wins1 >= 2) {
      finishWinner = f1Name;
      finishMethod = wins1 === 3 ? 'Decision (Unanimous)' : 'Decision (Split)';
    } else if (wins2 >= 2) {
      finishWinner = f2Name;
      finishMethod = wins2 === 3 ? 'Decision (Unanimous)' : 'Decision (Split)';
    } else if (wins1 === 1 && wins2 === 1) {
      // 1-1-1 true split draw — pick winner by total points
      finishWinner = total1 >= total2 ? f1Name : f2Name;
      finishMethod = 'Decision (Split)';
    } else {
      // All 3 cards drawn — pick winner by total, call it majority
      finishWinner = total1 >= total2 ? f1Name : f2Name;
      finishMethod = 'Decision (Majority)';
    }
  }

  const winner = finishWinner!;
  const loser = winner === f1Name ? f2Name : f1Name;
  const summary = generateSummary(rounds, winner, loser, finishMethod!, finishRound, finishTime, scorecards);

  return {
    fighter1: f1Name,
    fighter2: f2Name,
    winner,
    loser,
    method: finishMethod!,
    finishRound,
    finishTime,
    rounds,
    scorecards,
    summary,
  };
}

// ── Decision Scoring ───────────────────────────────────────────────────────

function scoreDecision(
  rounds: SimRound[],
  f1Name: string,
  f2Name: string,
  rng: SeededRandom,
): Scorecard[] {
  const judgeNames = ['Judge A', 'Judge B', 'Judge C'];
  // Each judge has slight bias toward different aspects
  const judgeBiases = [
    { striking: 1.0, grappling: 1.0 },   // balanced
    { striking: 1.15, grappling: 0.85 },  // favors striking
    { striking: 0.85, grappling: 1.15 },  // favors grappling
  ];

  return judgeNames.map((name, j) => {
    const bias = judgeBiases[j];
    const roundScores: { fighter1: number; fighter2: number }[] = [];

    for (const round of rounds) {
      const s1 = round.fighter1Stats;
      const s2 = round.fighter2Stats;

      // Effective scoring with judge bias
      const f1Score = (s1.sigStrikesLanded * 1.0 * bias.striking)
        + (s1.knockdowns * 5.0 * bias.striking)
        + (s1.takedownsLanded * 2.0 * bias.grappling)
        + (s1.controlTime * 0.10 * bias.grappling);

      const f2Score = (s2.sigStrikesLanded * 1.0 * bias.striking)
        + (s2.knockdowns * 5.0 * bias.striking)
        + (s2.takedownsLanded * 2.0 * bias.grappling)
        + (s2.controlTime * 0.10 * bias.grappling);

      // Each judge has meaningful random variance on close rounds
      // This prevents 3 identical cards and makes split decisions possible
      const noise = (rng.next() - 0.5) * 4.0;

      if (f1Score + noise > f2Score) {
        const margin = (f1Score - f2Score) / Math.max(f1Score, 1);
        roundScores.push({
          fighter1: 10,
          fighter2: margin > 0.4 || s1.knockdowns >= 2 ? 8 : 9,
        });
      } else {
        const margin = (f2Score - f1Score) / Math.max(f2Score, 1);
        roundScores.push({
          fighter1: margin > 0.4 || s2.knockdowns >= 2 ? 8 : 9,
          fighter2: 10,
        });
      }
    }

    return {
      judge: name,
      rounds: roundScores,
      total: {
        fighter1: roundScores.reduce((sum, r) => sum + r.fighter1, 0),
        fighter2: roundScores.reduce((sum, r) => sum + r.fighter2, 0),
      },
    };
  });
}

// ── Summary Generator ──────────────────────────────────────────────────────

function generateSummary(
  rounds: SimRound[],
  winner: string,
  loser: string,
  method: string,
  finishRound?: number,
  finishTime?: string,
  scorecards?: Scorecard[],
): string {
  const totalRounds = rounds.length;
  const f1TotalStrikes = rounds.reduce((s, r) => s + r.fighter1Stats.sigStrikesLanded, 0);
  const f2TotalStrikes = rounds.reduce((s, r) => s + r.fighter2Stats.sigStrikesLanded, 0);
  const f1TotalTd = rounds.reduce((s, r) => s + r.fighter1Stats.takedownsLanded, 0);
  const f2TotalTd = rounds.reduce((s, r) => s + r.fighter2Stats.takedownsLanded, 0);
  const f1TotalKd = rounds.reduce((s, r) => s + r.fighter1Stats.knockdowns, 0);
  const f2TotalKd = rounds.reduce((s, r) => s + r.fighter2Stats.knockdowns, 0);

  const winnerIsF1 = winner === rounds[0].events?.[0]?.fighter || f1TotalStrikes >= f2TotalStrikes;

  if (finishRound && finishTime) {
    if (method.startsWith('KO/TKO')) {
      return `${winner} stops ${loser} at ${finishTime} of Round ${finishRound}. ` +
        `The ${finishRound === 1 ? 'early' : finishRound <= 2 ? 'second-round' : 'late'} stoppage came after ` +
        `${winner} landed ${winnerIsF1 ? f1TotalStrikes : f2TotalStrikes} significant strikes across ${finishRound} round${finishRound > 1 ? 's' : ''}.`;
    } else {
      return `${winner} submits ${loser} at ${finishTime} of Round ${finishRound}. ` +
        `Control on the ground proved decisive, with ${winner} using superior grappling to force the tap.`;
    }
  }

  // Decision
  const scoreStr = scorecards
    ? scorecards.map(sc => `${sc.total.fighter1}-${sc.total.fighter2}`).join(', ')
    : '';

  return `${winner} defeats ${loser} by ${method} (${scoreStr}). ` +
    `Over ${totalRounds} rounds, the fight featured ${f1TotalStrikes + f2TotalStrikes} total significant strikes` +
    `${f1TotalTd + f2TotalTd > 0 ? ` and ${f1TotalTd + f2TotalTd} takedowns` : ''}.`;
}
