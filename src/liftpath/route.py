"""A multi-week route (BUILD2 Phase A). Each step calls recommend() on a projected state.

The next score band comes from train students who were in the same state and did the
step action. Only train points enter the transitions, so no test outcome enters a route.
Item examples use clicks only, never outcomes.
"""

from collections.abc import Callable
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import ABSTAIN, NONE_BAND, RECOMMEND
from liftpath.recommend import State, label, recommend
from liftpath.recover import ACTIVE_DAY_SQL, WEEK_DAYS, explain_recovery
from liftpath.states import action_of

KEEP = "_keep"
KEEP_LABEL = "Keep your current plan"
SCORE_ORDER = ["none", "low", "mid", "high"]
GOALS = ("goal_pass", "goal_distinction")
PLAN_EFFORTS = ("low", "mid", "high")
PROJECTION_NOTE = "Projection from past students, not a guarantee."
ITEM_NOTE = "Schedule rebuilt from course activity. A real LMS has the exact calendar."
ITEMS_PER_STEP = 3
# Back-off for projections: (same module only, week window half width).
PROJECTION_LEVELS = ((True, 0), (True, 1), (False, 1))
TRANSITION_KEYS = ["module", "week", "score_band", "next_effort_band", "action",
                   "next_week_block", "next_score_band"]

SCHEDULE_SQL = """
WITH active AS ({active_day_sql}),
clicks AS (SELECT course_id, item_id, sum(clicks) AS clicks FROM events GROUP BY ALL)
SELECT a.course_id, a.item_id, a.item_type, a.active_day,
       COALESCE(c.clicks, 0) AS clicks
FROM active a LEFT JOIN clicks c USING (course_id, item_id)
WHERE a.active_day IS NOT NULL
ORDER BY a.course_id, a.item_id
"""


@dataclass(frozen=True)
class RouteStep:
    week: int
    status: str
    action: str | None
    label: str
    score_band: str
    lift: float | None
    ci_low: float | None
    ci_high: float | None
    items: tuple[int, ...]
    level: int


@dataclass(frozen=True)
class Route:
    steps: tuple[RouteStep, ...]
    projected_route: float
    projected_typical: float
    effort: str
    goal: str
    stop_reason: str


@dataclass(frozen=True)
class RescueCard:
    assessment_id: int
    score: float
    action: str
    label: str
    lift: float
    ci_low: float
    ci_high: float
    items: tuple[int, ...]
    rationale: str


def score_transitions(points: pd.DataFrame, candidates: list[str], cfg: Config) -> pd.DataFrame:
    """Counts of (state, next effort, action) to the next week's block and score band.

    points must be train points. A step links (course_id, student_id, week) to week + 1.
    The action KEEP holds all points in the cell. k_<goal> counts the linked points that
    reached the goal.
    """
    nxt = points[["course_id", "student_id", "week", "week_block", "score_band"]].rename(
        columns={"week_block": "next_week_block", "score_band": "next_score_band"})
    nxt = nxt.assign(week=nxt["week"] - 1)
    linked = points.merge(nxt, on=["course_id", "student_id", "week"])
    linked = linked[linked["next_effort_band"] != NONE_BAND]
    keys = [k for k in TRANSITION_KEYS if k != "action"]
    parts = []
    for action in [KEEP, *candidates]:
        rows = linked if action == KEEP else linked[linked[f"act_{action}"]]
        counts = rows.groupby(keys, as_index=False).agg(
            n=("week", "size"), **{f"k_{g}": (g, "sum") for g in GOALS})
        parts.append(counts.assign(action=action))
    table = pd.concat(parts, ignore_index=True)[[*TRANSITION_KEYS, "n",
                                                 *[f"k_{g}" for g in GOALS]]]
    return table.astype({"n": "int64", **{f"k_{g}": "int64" for g in GOALS}})


def item_schedule(con: duckdb.DuckDBPyConnection, cfg: Config) -> pd.DataFrame:
    """Items with their active week (SPEC 13 active day) and total clicks per course.

    Columns: course_id, item_id, item_type, action, active_day, active_week, clicks.
    """
    sql = SCHEDULE_SQL.format(active_day_sql=ACTIVE_DAY_SQL.format(week_days=WEEK_DAYS))
    items = con.execute(sql).df()
    items["action"] = action_of(items["item_type"], cfg)
    items["active_week"] = (items["active_day"] // WEEK_DAYS).astype("int64")
    items["clicks"] = items["clicks"].astype("int64")
    return items[["course_id", "item_id", "item_type", "action", "active_day",
                  "active_week", "clicks"]]


def step_items(schedule: pd.DataFrame, course_id: str, action: str, week: int) -> tuple:
    """Top items of the type at the step week, else at the nearest week within 1 week."""
    rows = schedule[(schedule["course_id"] == course_id) & (schedule["action"] == action)]
    rows = rows.assign(distance=(rows["active_week"] - week).abs())
    rows = rows[rows["distance"] <= 1]
    if rows.empty:
        return ()
    nearest = rows[rows["distance"] == rows["distance"].min()]
    top = nearest.sort_values(["clicks", "item_id"], ascending=[False, True])
    return tuple(int(i) for i in top["item_id"].head(ITEMS_PER_STEP))


def scope_rows(transitions: pd.DataFrame, module: str, week: int, level: int) -> pd.DataFrame:
    same_module, half_width = PROJECTION_LEVELS[level]
    rows = transitions[transitions["week"].between(week - half_width, week + half_width)]
    return rows[rows["module"] == module] if same_module else rows


def mode(counts: pd.Series, order: list[str] | None = None) -> str:
    """The value with the highest count. Ties go to the first value in order."""
    if order is not None:
        counts = counts.reindex([v for v in order if v in counts.index])
    return str(counts.idxmax())


@dataclass(frozen=True)
class Projection:
    block: str
    bands: pd.Series  # share of each next score band, in SCORE_ORDER
    level: int
    source: str  # the step action, or KEEP when the action rows lack support


def project(transitions: pd.DataFrame, module: str, week: int, score_band: str,
            effort: str, action: str, cfg: Config) -> Projection | None:
    """The next week block and score band shares, or None if nothing has min_count points.

    At each back-off level the action rows come first. If they lack support, the KEEP rows
    of the same level come next, before the week window widens.
    """
    for level in range(len(PROJECTION_LEVELS)):
        scope = scope_rows(transitions, module, week, level)
        scope = scope[(scope["score_band"] == score_band)
                      & (scope["next_effort_band"] == effort)]
        for source in dict.fromkeys([action, KEEP]):
            rows = scope[scope["action"] == source]
            if rows["n"].sum() < cfg.min_count:
                continue
            counts = rows.groupby("next_score_band")["n"].sum().reindex(SCORE_ORDER,
                                                                          fill_value=0)
            return Projection(block=next_block(transitions, module, week, rows),
                              bands=counts / counts.sum(), level=level, source=source)
    return None


def propagate(pj: "Projector", module: str, week: int, bands: pd.Series, effort: str,
              action: str) -> tuple[str, pd.Series] | None:
    """Mix the projections of every current score band, weighted by its share.

    None if the most likely band has no projection. Other bands without one drop out.
    """
    top = mode(bands[bands > 0], SCORE_ORDER)
    head = pj.project(module, week, top, effort, action)
    if head is None:
        return None
    mixed = pd.Series(0.0, index=SCORE_ORDER)
    for band, share in bands[bands > 0].items():
        proj = head if band == top else pj.project(module, week, band, effort, action)
        if proj is not None:
            mixed += share * proj.bands
    return head.block, mixed / mixed.sum()


def next_block(transitions: pd.DataFrame, module: str, week: int,
               fallback: pd.DataFrame) -> str:
    """The week block of week + 1 in the module. Other modules only if the module has none."""
    own = transitions[(transitions["module"] == module) & (transitions["week"] == week)
                      & (transitions["action"] == KEEP)]
    rows = own if not own.empty else fallback
    return mode(rows.groupby("next_week_block")["n"].sum())


def goal_rate(transitions: pd.DataFrame, module: str, week: int, score_band: str,
              effort: str, goal: str, cfg: Config) -> float:
    """Smoothed goal rate (SPEC 10 prior) of train points at (module, week, score, effort).

    The points are the targets of KEEP transitions from week - 1. The prior is the goal
    rate of all targets in the same scope. The scope backs off like a projection.
    """
    keep = transitions[transitions["action"] == KEEP]
    for level in range(len(PROJECTION_LEVELS)):
        scope = scope_rows(keep, module, week - 1, level)
        rows = scope[(scope["next_score_band"] == score_band)
                     & (scope["next_effort_band"] == effort)]
        if rows["n"].sum() >= cfg.min_count or level == len(PROJECTION_LEVELS) - 1:
            if scope["n"].sum() == 0:
                return np.nan
            prior = scope[f"k_{goal}"].sum() / scope["n"].sum()
            m = cfg.prior_strength
            return float((rows[f"k_{goal}"].sum() + m * prior) / (rows["n"].sum() + m))
    return np.nan


@dataclass(frozen=True)
class Projector:
    """The three lookups a route needs. Built from raw transitions or from precomputed tables.

    The app ships only the tables, because the raw transitions hold counts below
    display_min_count (SPEC 19). A projection itself needs min_count points.
    """
    project: Callable[[str, int, str, str, str], Projection | None]
    goal_rate: Callable[[str, int, str, str, str], float]
    last_week: Callable[[str], int | None]


def transitions_projector(transitions: pd.DataFrame, cfg: Config) -> Projector:
    last = transitions.groupby("module")["week"].max()
    return Projector(
        project=lambda m, w, b, e, a: project(transitions, m, w, b, e, a, cfg),
        goal_rate=lambda m, w, b, e, g: goal_rate(transitions, m, w, b, e, g, cfg),
        last_week=lambda m: int(last[m]) if m in last.index else None)


def projection_tables(transitions: pd.DataFrame,
                      cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every projection and goal rate a route can ask for, as rows of shares and rates.

    Projections: per (module, week, score band, plan effort, action). Goal rates: per
    (module, week, score band, plan effort, goal), for weeks 0 to the last week of any
    module + 1, because test presentations can run longer than the train ones and the
    goal rate then backs off to other modules.
    """
    proj_rows, rate_rows = [], []
    actions = sorted(transitions["action"].unique())
    rate_weeks = int(transitions["week"].max()) + 2
    for module, last in transitions.groupby("module")["week"].max().items():
        for week in range(rate_weeks):
            for band in SCORE_ORDER:
                for effort in PLAN_EFFORTS:
                    for goal in GOALS:
                        rate_rows.append((module, week, band, effort, goal, goal_rate(
                            transitions, module, week, band, effort, goal, cfg)))
                    if week > last:
                        continue
                    for action in actions:
                        p = project(transitions, module, week, band, effort, action, cfg)
                        if p is not None:
                            proj_rows.append((module, week, band, effort, action, p.block,
                                              p.level, p.source, *p.bands.to_numpy()))
    keys = ["module", "week", "score_band", "effort", "action"]
    projections = pd.DataFrame(proj_rows, columns=[*keys, "block", "level", "source",
                                                   *[f"share_{b}" for b in SCORE_ORDER]])
    rates = pd.DataFrame(rate_rows, columns=[*keys[:4], "goal", "rate"])
    return projections, rates


def table_projector(projections: pd.DataFrame, rates: pd.DataFrame) -> Projector:
    shares = projections[[f"share_{b}" for b in SCORE_ORDER]].to_numpy()
    keys = zip(projections["module"], projections["week"], projections["score_band"],
               projections["effort"], projections["action"], strict=True)
    found = {
        key: Projection(block=block, bands=pd.Series(row, index=SCORE_ORDER), level=int(level),
                        source=source)
        for key, block, level, source, row in zip(
            keys, projections["block"], projections["level"], projections["source"], shares,
            strict=True)}
    rate = rates.set_index(["module", "week", "score_band", "effort", "goal"])["rate"].to_dict()
    last = projections.groupby("module")["week"].max()
    return Projector(
        project=lambda m, w, b, e, a: found.get((m, w, b, e, a)),
        goal_rate=lambda m, w, b, e, g: float(rate.get((m, w, b, e, g), np.nan)),
        last_week=lambda m: int(last[m]) if m in last.index else None)


def expected_rate(pj: "Projector", module: str, week: int, bands: pd.Series, effort: str,
                  goal: str) -> float:
    """The goal rate of each score band, weighted by the band share."""
    shares = bands[bands > 0]
    rates = [pj.goal_rate(module, week, b, effort, goal) for b in shares.index]
    return float(np.dot(shares.to_numpy(), rates))


def plan_effort(effort_band: str, effort: str | None) -> str:
    chosen = effort or effort_band
    return "low" if chosen == NONE_BAND else chosen


def start_bands(score_band: str) -> pd.Series:
    return pd.Series([float(b == score_band) for b in SCORE_ORDER], index=SCORE_ORDER)


def typical_bands(pj: "Projector", module: str, week: int, last_week: int,
                  bands: pd.Series, effort: str) -> tuple[int, pd.Series]:
    """Project score band shares with all points (KEEP) from week up to last_week."""
    while week < last_week:
        nxt = propagate(pj, module, week, bands, effort, KEEP)
        if nxt is None:
            break
        _, bands = nxt
        week += 1
    return week, bands


def plan_route(student_point: pd.Series, goal: str, tables: dict[int, pd.DataFrame],
               transitions: "pd.DataFrame | Projector", schedule: pd.DataFrame, cfg: Config,
               effort: str | None = None) -> Route:
    """Route of up to plan_horizon_weeks steps from the student's decision point.

    Each step recommends for the most likely score band. The projection carries the share
    of every band, so the projected rates use the full spread.
    """
    module, course_id = student_point["module"], student_point["course_id"]
    start_week = int(student_point["week"])
    plan = plan_effort(student_point["effort_band"], effort)
    week, block = start_week, student_point["week_block"]
    bands = start_bands(student_point["score_band"])
    effort_now = student_point["effort_band"]
    steps, stop_reason = [], "The route reached the plan horizon."
    pj = (transitions if isinstance(transitions, Projector)
          else transitions_projector(transitions, cfg))
    last = pj.last_week(module)
    last_source = start_week - 1 if last is None else last

    for _ in range(cfg.plan_horizon_weeks):
        band = mode(bands[bands > 0], SCORE_ORDER)
        rec = recommend(State(module, block, band, effort_now), goal, tables, cfg)
        if rec.status == ABSTAIN:
            stop_reason = f"Not enough similar students to compare at week {week}."
            break
        est = rec.estimate
        action = est.action if rec.status == RECOMMEND else KEEP
        steps.append(RouteStep(
            week=week, status=rec.status, action=est.action if est else None,
            label=label(action) if est else KEEP_LABEL, score_band=band,
            lift=est.lift if est else None, ci_low=est.ci_low if est else None,
            ci_high=est.ci_high if est else None,
            items=step_items(schedule, course_id, action, week) if est else (),
            level=est.level if est else -1))
        if week > last_source:
            stop_reason = f"The course ends at week {week}."
            break
        nxt = propagate(pj, module, week, bands, plan, action)
        if nxt is None:
            stop_reason = f"Not enough past students to project week {week + 1}."
            break
        block, bands = nxt
        week, effort_now = week + 1, plan

    if not steps:
        return Route((), np.nan, np.nan, plan, goal, stop_reason)
    typical_week, typical = typical_bands(pj, module, start_week, week,
                                          start_bands(student_point["score_band"]), plan)
    return Route(
        steps=tuple(steps),
        projected_route=expected_rate(pj, module, week, bands, plan, goal),
        projected_typical=expected_rate(pj, module, typical_week, typical, plan, goal),
        effort=plan, goal=goal, stop_reason=stop_reason)


def rescue_rows(points: pd.DataFrame, recovery: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """The recovery row behind the rescue card of each point, if there is one.

    points: course_id, student_id and week. The row is the latest low score whose window
    holds the end of the week (due_day <= week_end < next_due_day), with status recommend.
    Returns the recovery columns plus week, one row per point that has a card.
    """
    keys = points[["course_id", "student_id", "week"]].drop_duplicates()
    rows = keys.merge(recovery, on=["course_id", "student_id"])
    week_end = WEEK_DAYS * rows["week"] + WEEK_DAYS - 1
    rows = rows[(rows["due_day"] <= week_end) & (rows["next_due_day"] > week_end)
                & (rows["score"] < cfg.low_score) & (rows["status"] == RECOMMEND)]
    rows = rows.sort_values("due_day").drop_duplicates(
        ["course_id", "student_id", "week"], keep="last")
    return rows.reset_index(drop=True)


def rescue_card(student_point: pd.Series, recovery: pd.DataFrame, schedule: pd.DataFrame,
                cfg: Config) -> RescueCard | None:
    """The recovery card for the student's latest low score, if it is a recommendation.

    recovery: recovery points with the resolved status, action and estimate columns.
    The latest score is the assessment whose window holds the end of the student's week.
    """
    point = pd.DataFrame([{k: student_point[k] for k in ("course_id", "student_id", "week")}])
    rows = rescue_rows(point, recovery, cfg)
    if rows.empty:
        return None
    row = rows.iloc[0]
    old = schedule[(schedule["course_id"] == row["course_id"])
                   & (schedule["action"] == row["action"])
                   & (schedule["active_day"] < row["due_day"])]
    top = old.sort_values(["clicks", "item_id"], ascending=[False, True])
    return RescueCard(
        assessment_id=int(row["assessment_id"]), score=float(row["score"]),
        action=row["action"], label=label(row["action"]), lift=float(row["lift"]),
        ci_low=float(row["ci_low"]), ci_high=float(row["ci_high"]),
        items=tuple(int(i) for i in top["item_id"].head(ITEMS_PER_STEP)),
        rationale=explain_recovery(row, row["module"], row["low_band"], cfg))
