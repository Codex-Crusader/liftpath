"""Recommendation rule and rationale text (SPEC sections 11 and 12)."""

from dataclasses import asdict, dataclass, replace

import pandas as pd

from liftpath.config import Config
from liftpath.lift import (
    ABSTAIN,
    LEVELS,
    NO_CLEAR_WINNER,
    RECOMMEND,
    best_actions,
    resolve_points,
)

LABELS = {
    "oucontent": "course pages", "resource": "files", "url": "external links",
    "subpage": "section pages", "forumng": "discussion forum", "quiz": "quizzes",
    "ouwiki": "wiki", "glossary": "glossary", "externalquiz": "external quizzes",
    "oucollaborate": "live sessions", "ouelluminate": "live sessions",
    "questionnaire": "questionnaires", "page": "pages", "dataplus": "data tools",
    "dualpane": "dual-pane pages", "htmlactivity": "interactive pages",
    "repeatactivity": "repeat activities", "sharedsubpage": "shared pages",
    "folder": "folders", "homepage": "course homepage",
}
GOAL_TEXT = {"goal_pass": "a pass", "goal_distinction": "a distinction",
             "goal_recover": "a pass mark on the next assessment"}
NO_CLEAR_WINNER_TEXT = "No clear winner. Continue your current plan."
ABSTAIN_TEXT = "Not enough similar students to compare."
BACK_OFF_NOTE = {1: " (compared across all weeks)", 2: " (compared across all courses)"}


@dataclass(frozen=True)
class State:
    module: str
    week_block: str
    score_band: str
    effort_band: str


@dataclass(frozen=True)
class LiftEstimate:
    action: str
    lift: float
    ci_low: float
    ci_high: float
    p1_avg: float
    p0_avg: float
    n_did: int
    n_did_not: int
    level: int


@dataclass(frozen=True)
class Recommendation:
    status: str  # recommend | no_clear_winner | abstain
    estimate: LiftEstimate | None
    rationale: str


def label(action: str) -> str:
    return LABELS.get(action, action)


def show_count(n: int, cfg: Config) -> str:
    return f"fewer than {cfg.display_min_count}" if n < cfg.display_min_count else f"{n:,}"


def situation(state: State, level: int) -> str:
    """The cell parts that the level keeps, in SPEC section 12 order."""
    kept = LEVELS[level]
    parts = []
    if "module" in kept:
        parts.append(state.module)
    if "week_block" in kept:
        parts.append(f"{state.week_block} weeks")
    parts.append("no scores yet" if state.score_band == "none" else f"{state.score_band} scores")
    parts.append("no activity this week" if state.effort_band == "none"
                 else f"{state.effort_band} effort")
    return f"({', '.join(parts)}){BACK_OFF_NOTE.get(level, '')}"


def explain(rec: Recommendation, state: State, goal: str, cfg: Config) -> str:
    if rec.status == ABSTAIN:
        return ABSTAIN_TEXT
    if rec.status == NO_CLEAR_WINNER:
        return NO_CLEAR_WINNER_TEXT
    e = rec.estimate
    return (
        f"Students in a similar situation {situation(state, e.level)} who studied about as "
        f"much as you did next week: those who used {label(e.action)} reached "
        f"{GOAL_TEXT.get(goal, goal)} {e.p1_avg:.0%} of the time. Those who did not reached it "
        f"{e.p0_avg:.0%} of the time. Lift: {e.lift:+.0%} (95% range {e.ci_low:+.0%} to "
        f"{e.ci_high:+.0%}). Based on {show_count(e.n_did, cfg)} and "
        f"{show_count(e.n_did_not, cfg)} students."
    )


def recommend_points(points: pd.DataFrame, goal: str, tables: dict[int, pd.DataFrame],
                     cfg: Config) -> pd.DataFrame:
    """Vectorized SPEC section 11: status, action, level and estimate per point."""
    return resolve_points(points, best_actions(tables, cfg))


def recommend(state: State, goal: str, tables: dict[int, pd.DataFrame],
              cfg: Config) -> Recommendation:
    row = recommend_points(pd.DataFrame([asdict(state)]), goal, tables, cfg).iloc[0]
    estimate = None
    if row["status"] == RECOMMEND:
        estimate = LiftEstimate(
            action=row["action"], lift=row["lift"], ci_low=row["ci_low"],
            ci_high=row["ci_high"], p1_avg=row["p1_avg"], p0_avg=row["p0_avg"],
            n_did=int(row["n_did"]), n_did_not=int(row["n_did_not"]), level=int(row["level"]))
    rec = Recommendation(status=row["status"], estimate=estimate, rationale="")
    return replace(rec, rationale=explain(rec, state, goal, cfg))
