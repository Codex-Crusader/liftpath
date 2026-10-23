"""A multi-week route (BUILD2 Phase A). Each step calls recommend() on a projected state.

The next score band comes from train students who were in the same state and did the
step action. Only train points enter the transitions, so no test outcome enters a route.
Item examples use clicks only, never outcomes.
"""

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


def project(transitions: pd.DataFrame, module: str, week: int, score_band: str,
            effort: str, action: str, cfg: Config) -> tuple[str, str, int] | None:
    """Next (week_block, score_band, level), or None if no level has min_count points."""
    for level in range(len(PROJECTION_LEVELS)):
        rows = scope_rows(transitions, module, week, level)
        rows = rows[(rows["score_band"] == score_band) & (rows["next_effort_band"] == effort)
                    & (rows["action"] == action)]
        if rows["n"].sum() < cfg.min_count:
            continue
        band = mode(rows.groupby("next_score_band")["n"].sum(), SCORE_ORDER)
        block = next_block(transitions, module, week, rows)
        return block, band, level
    return None


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


def plan_effort(effort_band: str, effort: str | None) -> str:
    chosen = effort or effort_band
    return "low" if chosen == NONE_BAND else chosen


def typical_state(transitions: pd.DataFrame, module: str, week: int, last_week: int,
                  score_band: str, effort: str, cfg: Config) -> tuple[int, str]:
    """Project score bands with all points (KEEP) from week up to last_week."""
    while week < last_week:
        nxt = project(transitions, module, week, score_band, effort, KEEP, cfg)
        if nxt is None:
            break
        _, score_band, _ = nxt
        week += 1
    return week, score_band


def plan_route(student_point: pd.Series, goal: str, tables: dict[int, pd.DataFrame],
               transitions: pd.DataFrame, schedule: pd.DataFrame, cfg: Config,
               effort: str | None = None) -> Route:
    """Route of up to plan_horizon_weeks steps from the student's decision point."""
    module, course_id = student_point["module"], student_point["course_id"]
    start_week, start_band = int(student_point["week"]), student_point["score_band"]
    plan = plan_effort(student_point["effort_band"], effort)
    week, block, band = start_week, student_point["week_block"], start_band
    effort_now = student_point["effort_band"]
    steps, stop_reason = [], "The route reached the plan horizon."
    module_weeks = transitions.loc[transitions["module"] == module, "week"]
    last_source = int(module_weeks.max()) if not module_weeks.empty else start_week - 1

    for _ in range(cfg.plan_horizon_weeks):
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
        nxt = project(transitions, module, week, band, plan, action, cfg)
        if nxt is None:
            stop_reason = f"Not enough past students to project week {week + 1}."
            break
        block, band, _ = nxt
        week, effort_now = week + 1, plan

    if not steps:
        return Route((), np.nan, np.nan, plan, goal, stop_reason)
    typical_week, typical_band = typical_state(transitions, module, start_week, week,
                                               start_band, plan, cfg)
    return Route(
        steps=tuple(steps),
        projected_route=goal_rate(transitions, module, week, band, plan, goal, cfg),
        projected_typical=goal_rate(transitions, module, typical_week, typical_band, plan,
                                    goal, cfg),
        effort=plan, goal=goal, stop_reason=stop_reason)


def rescue_card(student_point: pd.Series, recovery: pd.DataFrame, schedule: pd.DataFrame,
                cfg: Config) -> RescueCard | None:
    """The recovery card for the student's latest low score, if it is a recommendation.

    recovery: recovery points with the resolved status, action and estimate columns.
    The latest score is the assessment whose window holds the end of the student's week.
    """
    week_end = WEEK_DAYS * int(student_point["week"]) + WEEK_DAYS - 1
    rows = recovery[(recovery["course_id"] == student_point["course_id"])
                    & (recovery["student_id"] == student_point["student_id"])
                    & (recovery["due_day"] <= week_end) & (recovery["next_due_day"] > week_end)]
    rows = rows[(rows["score"] < cfg.low_score) & (rows["status"] == RECOMMEND)]
    if rows.empty:
        return None
    row = rows.sort_values("due_day").iloc[-1]
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
