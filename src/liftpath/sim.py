"""Simulator and learning loop (BUILD2 Phase B).

The weekly loop follows the SPEC 16 generator, with the constants of SyntheticParams. A
policy recommends at the end of each week. A student follows a recommendation with
probability sim_compliance in the next week.

Two random streams:
- The world stream is seeded by (world, cohort). It draws all world randomness before the
  loop, so every policy sees the same students, clicks and coin flips.
- The policy stream is seeded by (world, cohort, policy). It holds the explore coin, the
  explore choice and the picks of the random policy.

rec_action and explored sit on the decision row of week w. That row's act_<a> columns
describe week w + 1, the week the recommendation is for.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from liftpath.adapters.synthetic import SyntheticParams, sigmoid
from liftpath.baselines import (
    make_liftpath,
    make_popular,
    make_random,
    make_raw_success,
    make_user_cf,
)
from liftpath.config import Config
from liftpath.evaluate import interval, student_draws
from liftpath.lift import (
    LEVELS,
    NONE_BAND,
    STUDENT_KEY,
    best_actions,
    estimate_lifts,
    lift_tables,
    resolve_points,
)
from liftpath.states import add_week_block, effort_bands, score_bands

WORLDS = ("standard", "hidden_confounder")
POLICIES = ("none", "random", "popular", "user_cf", "raw_success", "liftpath",
            "liftpath_explore")
GOAL = "goal_pass"
WEEK_DAYS = 7
PRESENTATION = "SIM"
ID_STRIDE = 1_000_000
# Hidden confounder: resource engagement depends on ability u only, not on clicks.
HIDDEN_ACTION = "resource"
HIDDEN_A, HIDDEN_B_U = -1.0, 1.5
TRACKED_ACTIONS = ("quiz", "resource")
TRUE_ACTION = "quiz"

Policy = Callable[[pd.DataFrame, int], tuple[pd.Series, np.ndarray]]


@dataclass(frozen=True)
class WorldDraws:
    """All world randomness of one cohort. Arrays are (students, weeks[, types])."""
    u: np.ndarray
    clicks: np.ndarray
    engage_u: np.ndarray
    comply_u: np.ndarray
    withdraws: np.ndarray
    withdraw_week: np.ndarray
    score_noise: np.ndarray
    outcome_u: np.ndarray


@dataclass(frozen=True)
class Cohort:
    points: pd.DataFrame
    students: pd.DataFrame  # course_id, student_id, goal_pass, goal_distinction, true_effect


def n_weeks(p: SyntheticParams) -> int:
    return int(np.ceil(p.length_days / WEEK_DAYS))


def world_draws(world: str, cohort: int, n: int, p: SyntheticParams, cfg: Config) -> WorldDraws:
    rng = np.random.default_rng([cfg.seed, WORLDS.index(world), cohort])
    weeks, types = n_weeks(p), len(p.engagement)
    u = rng.normal(0, 1, n)
    withdraws = rng.random(n) < p.withdraw_share
    withdraw_week = rng.integers(p.withdraw_first_week, p.withdraw_last_week + 1, n)
    active = ~withdraws[:, None] | (np.arange(weeks)[None, :] <= withdraw_week[:, None])
    noise = rng.normal(0, p.click_noise_sd, (n, weeks))
    clicks = rng.poisson(np.exp(p.click_base + p.click_ability * u[:, None] + noise)) * active
    return WorldDraws(
        u=u, clicks=clicks, engage_u=rng.random((n, weeks, types)),
        comply_u=rng.random((n, weeks)), withdraws=withdraws, withdraw_week=withdraw_week,
        score_noise=rng.normal(0, p.score_noise_sd, (n, len(p.tma_due))),
        outcome_u=rng.random(n))


def engage_probs(world: str, draws: WorldDraws, p: SyntheticParams) -> np.ndarray:
    """Natural engagement probability per (student, week, type)."""
    log_c = np.log1p(draws.clicks)
    probs = np.stack([sigmoid(e.a + e.b * log_c) for e in p.engagement.values()], axis=2)
    if world == "hidden_confounder":
        k = list(p.engagement).index(HIDDEN_ACTION)
        probs[:, :, k] = sigmoid(HIDDEN_A + HIDDEN_B_U * draws.u)[:, None]
    return probs


def sim_candidates(p: SyntheticParams, cfg: Config) -> list[str]:
    """SPEC 8 for the simulator: the top types by natural clicks in standard cohort 0."""
    draws = world_draws("standard", 0, cfg.sim_dev_students, p, cfg)
    engaged = (draws.engage_u < engage_probs("standard", draws, p)) & (draws.clicks > 0)[..., None]
    per_type = type_clicks(engaged, draws.clicks).sum(axis=(0, 1))
    order = sorted((t for t in p.engagement if t not in cfg.exclude_types),
                   key=lambda t: -per_type[list(p.engagement).index(t)])
    return order[:cfg.n_candidates]


def type_clicks(engaged: np.ndarray, clicks: np.ndarray) -> np.ndarray:
    """Clicks per engaged type: max(1, c // number of engaged types) (SPEC 16)."""
    n_engaged = engaged.sum(axis=2)
    per_type = np.maximum(1, clicks // np.maximum(n_engaged, 1))
    return engaged * per_type[..., None]


def tma_scores(draws: WorldDraws, quiz: np.ndarray, p: SyntheticParams) -> np.ndarray:
    """(students, TMAs) scores, NaN where the student did not submit."""
    week_end = WEEK_DAYS * np.arange(quiz.shape[1]) + WEEK_DAYS - 1
    out = np.full((len(draws.u), len(p.tma_due)), np.nan)
    for k, due in enumerate(p.tma_due):
        q = quiz[:, week_end < due].sum(axis=1)
        raw = (p.score_base + p.score_ability * draws.u + p.score_per_quiz_week * q
               + draws.score_noise[:, k])
        submitted = ~draws.withdraws | (WEEK_DAYS * draws.withdraw_week + WEEK_DAYS - 1 >= due)
        out[submitted, k] = np.clip(np.round(raw), 0, p.score_max)[submitted]
    return out


def week_state(cohort: int, week: int, draws: WorldDraws, engaged: np.ndarray,
               tclicks: np.ndarray, types: list[str], candidates: list[str],
               p: SyntheticParams, cfg: Config) -> pd.DataFrame:
    """SPEC 7 state of the students registered at the end of week. Uses weeks <= week."""
    n = len(draws.u)
    total = tclicks.sum(axis=2)
    registered = ~draws.withdraws | (week < draws.withdraw_week)
    course_id = f"SYN_{PRESENTATION}{cohort}"
    clicks_week = total[:, week]
    has = clicks_week > 0
    bands = pd.Series(NONE_BAND, index=range(n), dtype=object)
    if has.any():
        totals = pd.DataFrame({"course_id": course_id, "week": week,
                               "clicks": clicks_week[has]}, index=np.flatnonzero(has))
        bands[totals.index] = effort_bands(totals)

    week_end = WEEK_DAYS * week + WEEK_DAYS - 1
    known = np.array(p.tma_due) <= week_end
    scores = tma_scores(draws, engaged[:, :, types.index("quiz")], p)[:, known]
    count = (~np.isnan(scores)).sum(axis=1)
    state = pd.DataFrame({
        "course_id": course_id, "module": p.module, "presentation": PRESENTATION,
        "split": "train", "student_id": cohort * ID_STRIDE + np.arange(n), "week": week,
        "n_weeks": n_weeks(p),
        "score_band": score_bands(count, np.nansum(scores, axis=1), cfg),
        "effort_band": bands.to_numpy(), "clicks_week": clicks_week})
    cum = tclicks[:, :week + 1].sum(axis=1)
    cum_total = cum.sum(axis=1)
    for a in candidates:
        state[f"cum_share_{a}"] = np.divide(cum[:, types.index(a)], cum_total,
                                            out=np.zeros(n), where=cum_total > 0)
    return add_week_block(state).drop(columns="n_weeks")[registered].reset_index(drop=True)


def simulate_cohort(world: str, cohort: int, n: int, policy: Policy | None,
                    candidates: list[str], cfg: Config,
                    p: SyntheticParams | None = None) -> Cohort:
    p = p or SyntheticParams()
    draws = world_draws(world, cohort, n, p, cfg)
    types = list(p.engagement)
    weeks = n_weeks(p)
    clicks = draws.clicks.copy()
    engaged = (draws.engage_u < engage_probs(world, draws, p)) & (clicks > 0)[..., None]
    active = ~draws.withdraws[:, None] | (np.arange(weeks)[None, :] <= draws.withdraw_week[:, None])
    rec_index = np.full((n, weeks), -1)
    explored = np.zeros((n, weeks), dtype=bool)
    states = []

    for week in range(weeks):
        if week > 0:
            rec = rec_index[:, week - 1]
            follow = (rec >= 0) & (draws.comply_u[:, week] < cfg.sim_compliance) & active[:, week]
            rows = np.flatnonzero(follow)
            engaged[rows, week, [types.index(candidates[r]) for r in rec[rows]]] = True
            clicks[rows, week] = np.maximum(clicks[rows, week], 1)
        if week > weeks - 2:
            continue
        tclicks = type_clicks(engaged[:, :week + 1], clicks[:, :week + 1])
        state = week_state(cohort, week, draws, engaged[:, :week + 1], tclicks, types,
                           candidates, p, cfg)
        idx = (state["student_id"] - cohort * ID_STRIDE).to_numpy()
        if policy is not None:
            actions, explore = policy(state, week)
            rec = np.array([candidates.index(a) if a is not None else -1 for a in actions])
            rec_index[idx, week] = rec
            explored[idx, week] = explore
        states.append(state)

    return finish_cohort(world, cohort, draws, engaged, clicks, rec_index, explored, states,
                         types, candidates, p)


def finish_cohort(world, cohort, draws, engaged, clicks, rec_index, explored, states, types,
                  candidates, p) -> Cohort:
    """Add next-week columns, outcomes, rec_action and explored to the weekly states."""
    n = len(draws.u)
    tclicks = type_clicks(engaged, clicks)
    total = tclicks.sum(axis=2)
    points = pd.concat(states, ignore_index=True)
    idx = (points["student_id"] - cohort * ID_STRIDE).to_numpy()
    nxt = points["week"].to_numpy() + 1

    course_id = f"SYN_{PRESENTATION}{cohort}"
    next_bands = {}
    for week in np.unique(nxt):
        has = total[:, week] > 0
        totals = pd.DataFrame({"course_id": course_id, "week": week,
                               "clicks": total[has, week]}, index=np.flatnonzero(has))
        next_bands[week] = pd.Series(effort_bands(totals) if has.any() else [],
                                     index=totals.index, dtype=object)
    points["next_effort_band"] = [next_bands[w].get(i, NONE_BAND) for i, w in zip(idx, nxt,
                                                                                 strict=True)]
    points["clicks_next"] = total[idx, nxt]
    for a in candidates:
        points[f"act_{a}"] = engaged[idx, nxt, types.index(a)]

    quiz_weeks = engaged[:, :, types.index("quiz")].sum(axis=1)
    logit = p.outcome_base + p.outcome_ability * draws.u + p.outcome_quiz_effect * (
        quiz_weeks - p.outcome_quiz_center)
    passed = (draws.outcome_u < sigmoid(logit)) & ~draws.withdraws
    distinction = passed & (logit > p.distinction_logit)
    # One more quiz week. Withdrawn students cannot reach the goal, so their effect is 0.
    effect = (sigmoid(logit + p.outcome_quiz_effect) - sigmoid(logit)) * ~draws.withdraws
    students = pd.DataFrame({"course_id": course_id,
                             "student_id": cohort * ID_STRIDE + np.arange(n),
                             "goal_pass": passed, "goal_distinction": distinction,
                             "true_effect": effect, "world": world, "cohort": cohort})
    points["goal_pass"] = passed[idx]
    points["goal_distinction"] = distinction[idx]
    rec = rec_index[idx, points["week"].to_numpy()]
    points["rec_action"] = pd.Series([candidates[r] if r >= 0 else None for r in rec],
                                     dtype=object)
    points["explored"] = explored[idx, points["week"].to_numpy()]
    return Cohort(points=points, students=students)


def wald_effects(decisions: pd.DataFrame, candidates: list[str], cfg: Config,
                 rng: np.random.Generator) -> pd.DataFrame:
    """Experimental effect per action from explored decisions (Wald, ITT / first stage).

    ITT_a and FS_a compare decisions with rec = a and rec != a. The interval is a cluster
    bootstrap over students (sim_boot runs). An effect is available only if FS_a >=
    sim_min_first_stage and both arms have at least min_count decisions.
    """
    columns = ["action", "itt", "first_stage", "effect", "ci_low", "ci_high", "n_rec",
               "n_other", "available"]
    if decisions.empty:
        return pd.DataFrame(columns=columns)
    students = decisions.groupby(STUDENT_KEY).ngroup().to_numpy()
    n_students = students.max() + 1
    draws = student_draws(n_students, replace(cfg, n_boot=cfg.sim_boot), rng)
    weights = np.vstack([np.ones(n_students), draws])
    goal = decisions[GOAL].to_numpy(float)
    rows = []
    for a in candidates:
        rec = (decisions["rec_action"] == a).to_numpy()
        act = decisions[f"act_{a}"].to_numpy(float)
        sums = np.stack([np.bincount(students, weights=v, minlength=n_students) for v in (
            rec, rec * goal, rec * act, ~rec, ~rec * goal, ~rec * act)], axis=1)
        n1, g1, x1, n0, g0, x0 = (weights @ sums).T
        with np.errstate(invalid="ignore", divide="ignore"):
            itt = g1 / n1 - g0 / n0
            fs = x1 / n1 - x0 / n0
            effect = np.where(fs > 0, itt / fs, np.nan)
        low, high = interval(effect[1:], cfg)
        available = bool(fs[0] >= cfg.sim_min_first_stage and n1[0] >= cfg.min_count
                         and n0[0] >= cfg.min_count)
        rows.append({"action": a, "itt": itt[0], "first_stage": fs[0], "effect": effect[0],
                     "ci_low": low, "ci_high": high, "n_rec": int(n1[0]),
                     "n_other": int(n0[0]), "available": available})
    return pd.DataFrame(rows, columns=columns)


def candidate_scores(points: pd.DataFrame, tables: dict[int, pd.DataFrame],
                     experimental: pd.DataFrame, candidates: list[str],
                     cfg: Config) -> pd.DataFrame:
    """Score, ci_low and ci_high per (point, candidate), with NaN for no estimate.

    The observational lift comes from the level that resolve_points picks for the point,
    with the SPEC 11 support rule. An available experimental effect replaces it.
    """
    level = resolve_points(points, best_actions(tables, cfg))["level"]
    grid = pd.DataFrame({"row": np.repeat(np.arange(len(points)), len(candidates)),
                         "action": np.tile(candidates, len(points))})
    parts = []
    for lv, cells in LEVELS.items():
        rows = np.flatnonzero(level.to_numpy() == lv)
        if len(rows) == 0:
            continue
        table = tables[lv]
        table = table[table[["n_did", "n_did_not"]].min(axis=1) >= cfg.min_count]
        sub = points.iloc[rows][cells].assign(row=rows)
        parts.append(sub.merge(table, on=cells)[["row", "action", "lift", "ci_low",
                                                 "ci_high"]])
    obs = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["row", "action", "lift", "ci_low", "ci_high"])
    scores = grid.merge(obs.rename(columns={"lift": "score"}), on=["row", "action"],
                        how="left")
    exp = experimental[experimental["available"].astype(bool)].set_index("action")
    use = scores["action"].isin(exp.index)
    if use.any():
        for col, src in (("score", "effect"), ("ci_low", "ci_low"), ("ci_high", "ci_high")):
            scores.loc[use, col] = scores.loc[use, "action"].map(exp[src].astype(float))
    return scores


def make_explore(tables: dict[int, pd.DataFrame], experimental: pd.DataFrame,
                 candidates: list[str], cfg: Config, rng: np.random.Generator) -> Policy:
    def policy(points: pd.DataFrame, week: int) -> tuple[pd.Series, np.ndarray]:
        n = len(points)
        scores = candidate_scores(points, tables, experimental, candidates, cfg)
        score = scores["score"].to_numpy(float).reshape(n, len(candidates))
        low = scores["ci_low"].to_numpy(float).reshape(n, len(candidates))
        high = scores["ci_high"].to_numpy(float).reshape(n, len(candidates))
        explored = rng.random(n) < cfg.sim_explore_share
        keys = rng.random((n, len(candidates)))

        allowed = np.isnan(score) | (high > 0)
        explore_pick = np.where(allowed, keys, -1.0).argmax(axis=1)
        explore_ok = allowed.any(axis=1)
        usable = ~np.isnan(score) & (low > 0)
        exploit_pick = np.where(usable, score, -np.inf).argmax(axis=1)
        exploit_ok = usable.any(axis=1)

        pick = np.where(explored, explore_pick, exploit_pick)
        ok = np.where(explored, explore_ok, exploit_ok)
        actions = [candidates[i] if good else None for i, good in zip(pick, ok, strict=True)]
        return pd.Series(actions, index=points.index, dtype=object), explored & ok
    return policy


def wrap(recommender) -> Policy:
    def policy(points: pd.DataFrame, week: int) -> tuple[pd.Series, np.ndarray]:
        return recommender(points), np.zeros(len(points), dtype=bool)
    return policy


def build_policy(name: str, train: pd.DataFrame, candidates: list[str], cfg: Config,
                 rng: np.random.Generator) -> tuple[Policy | None, pd.DataFrame]:
    """The policy for the next cohort, and the Wald estimates it uses (explore only)."""
    no_estimates = pd.DataFrame()
    if name == "none":
        return None, no_estimates
    if name == "random":
        def random_policy(points: pd.DataFrame, week: int):
            pick = make_random(candidates, int(rng.integers(2**32)))(points)
            return pick, np.zeros(len(points), dtype=bool)
        return random_policy, no_estimates
    if name == "popular":
        return wrap(make_popular(train, candidates, cfg)), no_estimates
    if name == "user_cf":
        return wrap(make_user_cf(train, candidates, cfg)), no_estimates
    if name == "raw_success":
        return wrap(make_raw_success(train, candidates, GOAL, cfg)), no_estimates
    tables = lift_tables(train, candidates, GOAL, cfg)
    if name == "liftpath":
        return wrap(make_liftpath(tables, GOAL, cfg)), no_estimates
    experimental = wald_effects(train[train["explored"]], candidates, cfg, rng)
    return make_explore(tables, experimental, candidates, cfg, rng), experimental


def cohort_metrics(world: str, policy: str, cohort: Cohort, candidates: list[str]) -> dict:
    recs = cohort.points["rec_action"].dropna()
    shares = recs.value_counts(normalize=True)
    row = {"world": world, "policy": policy, "cohort": int(cohort.students["cohort"].iloc[0]),
           "pass_rate": cohort.students["goal_pass"].mean(),
           "distinction_rate": cohort.students["goal_distinction"].mean(),
           "rec_rate": cohort.points["rec_action"].notna().mean(),
           "quiz_share": shares.get(TRUE_ACTION, 0.0),
           "explored_share": cohort.points["explored"].mean(),
           "true_effect": cohort.students["true_effect"].mean()}
    row.update({f"share_{a}": shares.get(a, 0.0) for a in candidates})
    return row


def observational(train: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Pooled effort-matched lift of the tracked actions (SPEC 10, no cell columns)."""
    out = estimate_lifts(train, [], "next_effort_band", [f"act_{a}" for a in TRACKED_ACTIONS],
                         GOAL, cfg)
    return out.assign(action=out["action"].str.removeprefix("act_"))


def run_world(world: str, cfg: Config, n_students: int, n_cohorts: int,
              policies: tuple[str, ...] = POLICIES,
              p: SyntheticParams | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Results per (policy, cohort) and the explore track estimates, for one world."""
    p = p or SyntheticParams()
    candidates = sim_candidates(p, cfg)
    shared = simulate_cohort(world, 0, n_students, None, candidates, cfg, p)
    results, estimates = [], []
    for name in policies:
        history = [shared]
        results.append(cohort_metrics(world, name, shared, candidates))
        for k in range(1, n_cohorts):
            rng = np.random.default_rng([cfg.seed, WORLDS.index(world), k,
                                         POLICIES.index(name), 1])
            train = pd.concat([c.points for c in history], ignore_index=True)
            policy, experimental = build_policy(name, train, candidates, cfg, rng)
            cohort = simulate_cohort(world, k, n_students, policy, candidates, cfg, p)
            history.append(cohort)
            results.append(cohort_metrics(world, name, cohort, candidates))
            if name == "liftpath_explore":
                estimates.append(track_estimates(world, k, train, experimental, cohort, cfg))
    estimates_frame = (pd.concat(estimates, ignore_index=True) if estimates
                       else pd.DataFrame())
    return pd.DataFrame(results), estimates_frame


def track_estimates(world: str, cohort: int, train: pd.DataFrame,
                    experimental: pd.DataFrame, run: Cohort, cfg: Config) -> pd.DataFrame:
    """The estimates the explore policy had before cohort k, next to the true effect."""
    obs = observational(train, cfg)
    rows = [{"kind": "observational", "action": r.action, "estimate": r.lift,
             "ci_low": r.ci_low, "ci_high": r.ci_high, "available": True}
            for r in obs.itertuples()]
    exp = experimental[experimental["action"].isin(TRACKED_ACTIONS)]
    rows += [{"kind": "experimental", "action": r.action, "estimate": r.effect,
              "ci_low": r.ci_low, "ci_high": r.ci_high, "available": r.available,
              "first_stage": r.first_stage, "n_rec": r.n_rec}
             for r in exp.itertuples()]
    true = run.students["true_effect"].mean()
    return pd.DataFrame(rows).assign(world=world, cohort=cohort,
                                     true_effect=lambda d: np.where(
                                         d["action"] == TRUE_ACTION, true, 0.0))


def expected_results(results: pd.DataFrame) -> dict[str, bool | float]:
    """The BUILD2 Phase B expected results, from the final cohort and all advised cohorts."""
    last = results["cohort"].max()
    final = results[results["cohort"] == last].set_index(["world", "policy"])["pass_rate"]
    advised = results[(results["cohort"] > 0) & (results["world"] == "hidden_confounder")]
    greedy = advised[advised["policy"] == "liftpath"]
    explore = advised[advised["policy"] == "liftpath_explore"]
    weights = greedy["rec_rate"]
    resource = float((greedy["share_resource"] * weights).sum() / weights.sum())
    explore_quiz_last = float(explore.loc[explore["cohort"] == last, "quiz_share"].iloc[0])
    return {
        "standard_liftpath_beats_raw_success":
            bool(final["standard", "liftpath"] > final["standard", "raw_success"]),
        "standard_liftpath_beats_user_cf":
            bool(final["standard", "liftpath"] > final["standard", "user_cf"]),
        "hidden_liftpath_resource_share": resource,
        "hidden_liftpath_resource_in_most": resource > 0.5,
        "hidden_explore_quiz_share_last": explore_quiz_last,
        "hidden_explore_shifts_to_quiz": explore_quiz_last > 0.5,
        "hidden_explore_beats_liftpath":
            bool(final["hidden_confounder", "liftpath_explore"]
                 > final["hidden_confounder", "liftpath"]),
    }
