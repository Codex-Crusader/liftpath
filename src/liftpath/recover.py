"""Recovery ("go back") after a low score (SPEC section 13).

build_recovery_points expects a connection where states.register_canonical already ran.
"""

import duckdb
import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import ABSTAIN, NO_CLEAR_WINNER, estimate_lifts
from liftpath.recommend import ABSTAIN_TEXT, GOAL_TEXT, NO_CLEAR_WINNER_TEXT, label, show_count
from liftpath.states import NONE_BAND, action_of, effort_bands, wide_by_action

RECOVERY_LEVELS: dict[int, list[str]] = {0: ["module", "low_band"], 1: ["low_band"]}
# SPEC section 13: very_low is a score below 20. low is 20 up to low_score.
VERY_LOW_MAX = 20
WEEK_DAYS = 7
KEY = ["course_id", "student_id", "assessment_id"]

TRIGGERS_SQL = """
WITH ordered AS (
    SELECT course_id, assessment_id, due_day,
           lead(assessment_id) OVER w AS next_assessment_id,
           lead(due_day) OVER w AS next_due_day
    FROM assessments
    WHERE kind <> 'Exam' AND due_day IS NOT NULL
    WINDOW w AS (PARTITION BY course_id ORDER BY due_day, assessment_id)
)
SELECT s.course_id, c.module, c.split, s.student_id, o.assessment_id, s.score,
       o.due_day, o.next_assessment_id, o.next_due_day, n.score AS next_score
FROM submissions s
JOIN ordered o USING (course_id, assessment_id)
JOIN course_split c USING (course_id)
LEFT JOIN submissions n
  ON n.course_id = s.course_id AND n.student_id = s.student_id
 AND n.assessment_id = o.next_assessment_id
WHERE s.score < {low_score} AND o.next_assessment_id IS NOT NULL
"""

# Active day: week_from * 7, else the click-weighted median click day in the course.
ACTIVE_DAY_SQL = """
WITH daily AS (
    SELECT course_id, item_id, day, sum(clicks) AS clicks FROM events GROUP BY ALL
), running AS (
    SELECT *, sum(clicks) OVER (PARTITION BY course_id, item_id ORDER BY day) AS cum,
              sum(clicks) OVER (PARTITION BY course_id, item_id) AS total
    FROM daily
), median AS (
    SELECT course_id, item_id, min(day) FILTER (WHERE cum >= total / 2) AS median_day
    FROM running GROUP BY ALL
)
SELECT i.course_id, i.item_id, i.item_type,
       COALESCE(i.week_from * {week_days}, m.median_day) AS active_day
FROM items i LEFT JOIN median m USING (course_id, item_id)
"""

WINDOW_CLICKS_SQL = """
SELECT t.course_id, t.student_id, t.assessment_id, a.item_type,
       a.active_day < t.due_day AS is_old, sum(e.clicks) AS clicks
FROM triggers t
JOIN events e
  ON e.course_id = t.course_id AND e.student_id = t.student_id
 AND e.day > t.due_day AND e.day <= t.next_due_day
JOIN active_days a ON a.course_id = e.course_id AND a.item_id = e.item_id
GROUP BY ALL
"""


def build_recovery_points(con: duckdb.DuckDBPyConnection, cfg: Config,
                          candidates: list[str]) -> pd.DataFrame:
    triggers = con.execute(TRIGGERS_SQL.format(low_score=cfg.low_score)).df()
    con.register("triggers", triggers)
    con.execute("CREATE OR REPLACE TEMP TABLE active_days AS "
                + ACTIVE_DAY_SQL.format(week_days=WEEK_DAYS))
    clicks = con.execute(WINDOW_CLICKS_SQL).df()
    con.unregister("triggers")

    clicks["action"] = action_of(clicks["item_type"], cfg)
    totals = clicks.groupby(KEY, as_index=False)["clicks"].sum()
    totals = totals[totals["clicks"] > 0]
    totals["effort_band"] = effort_bands(totals, by=("course_id", "assessment_id"))
    # wide_by_action groups by (course_id, student_id, week); the assessment takes the
    # place of the week here.
    old = clicks[clicks["is_old"].fillna(False).astype(bool)].rename(
        columns={"assessment_id": "week"})
    old_wide = wide_by_action(old, candidates).drop(columns="total").rename(
        columns={"week": "assessment_id"})

    points = (triggers.merge(totals.rename(columns={"clicks": "window_clicks"}), on=KEY,
                             how="left")
              .merge(old_wide, on=KEY, how="left"))
    points["window_clicks"] = points["window_clicks"].fillna(0).astype("int64")
    points["effort_band"] = points["effort_band"].fillna(NONE_BAND)
    for action in candidates:
        points[f"rev_{action}"] = points.pop(action).fillna(0) > 0
    points["low_band"] = np.where(points["score"] < VERY_LOW_MAX, "very_low", "low")
    points["goal_recover"] = points["next_score"].ge(cfg.low_score)
    columns = ["course_id", "module", "split", "student_id", "assessment_id",
               "next_assessment_id", "score", "next_score", "due_day", "next_due_day",
               "low_band", "window_clicks", "effort_band",
               *[f"rev_{a}" for a in candidates], "goal_recover"]
    return points[columns]


def recovery_tables(points: pd.DataFrame, candidates: list[str],
                    cfg: Config) -> dict[int, pd.DataFrame]:
    """Recovery lift per candidate at each level, controlled for window effort."""
    treatments = [f"rev_{a}" for a in candidates]
    tables = {}
    for level, cells in RECOVERY_LEVELS.items():
        table = estimate_lifts(points, cells, "effort_band", treatments, "goal_recover", cfg)
        table["action"] = table["action"].str.removeprefix("rev_")
        tables[level] = table
    return tables


def explain_recovery(rec: pd.Series, module: str, low_band: str, cfg: Config) -> str:
    """Rationale for one resolved recovery point, in the SPEC section 12 style."""
    if rec["status"] == ABSTAIN:
        return ABSTAIN_TEXT
    if rec["status"] == NO_CLEAR_WINNER:
        return NO_CLEAR_WINNER_TEXT
    band = (f"a score below {VERY_LOW_MAX}" if low_band == "very_low"
            else f"a score from {VERY_LOW_MAX} to {cfg.low_score - 1}")
    where = f"{module}, {band}" if rec["level"] == 0 else f"{band}) (compared across all courses"
    return (
        f"Students in a similar situation ({where}) who studied about as much as you did "
        f"before the next assessment: those who went back to earlier {label(rec['action'])} "
        f"reached {GOAL_TEXT['goal_recover']} {rec['p1_avg']:.0%} of the time. Those who did "
        f"not reached it {rec['p0_avg']:.0%} of the time. Lift: {rec['lift']:+.0%} (95% range "
        f"{rec['ci_low']:+.0%} to {rec['ci_high']:+.0%}). Based on "
        f"{show_count(int(rec['n_did']), cfg)} and {show_count(int(rec['n_did_not']), cfg)} "
        f"low-score cases."
    )
