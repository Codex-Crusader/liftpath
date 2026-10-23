"""Trap comparison (BUILD2 Phase C): common advice next to its effort-matched lift."""

import numpy as np
import pandas as pd

from liftpath.baselines import make_raw_success, make_user_cf
from liftpath.config import Config
from liftpath.lift import RECOMMEND, best_actions, point_lifts, resolve_points
from liftpath.recommend import label

TRAP_METHODS = ("user_cf", "raw_success")
LEADS = {"user_cf": "Similar students often do {label}.",
         "raw_success": "Students who reached the goal often used {label}."}
AGREE = {"user_cf": "Both methods agree: {label}.",
         "raw_success": "Students who reached the goal also often used {label}."}
NO_CLEAR_HELP = "No clear help."
NO_ESTIMATE = "There is not enough matched data to measure its lift."
TRAP_COLS = ("action", "lift", "ci_low", "ci_high")


def trap_lines(row: pd.Series, goal: str, liftpath_action: str | None) -> list[str]:
    """The trap card lines for one app student row, one per method that gives advice."""
    lines = [trap_text(m, liftpath_action, *(row[f"{goal}_{m}_{c}"] for c in TRAP_COLS))
             for m in TRAP_METHODS]
    return [line for line in lines if line is not None]


def trap_text(method: str, liftpath_action: str | None, other_action: str | None,
              lift: float, ci_low: float, ci_high: float) -> str | None:
    """The trap card line for one method. None if the method gives no advice."""
    if other_action is None or pd.isna(other_action):
        return None
    if other_action == liftpath_action:
        return AGREE[method].format(label=label(other_action))
    lead = LEADS[method].format(label=label(other_action))
    if lift is None or pd.isna(lift):
        return f"{lead} {NO_ESTIMATE}"
    text = (f"{lead} With matched effort, its lift is {lift:+.0%} "
            f"(range {ci_low:+.0%} to {ci_high:+.0%}).")
    return f"{text} {NO_CLEAR_HELP}" if ci_low <= 0 <= ci_high else text


def trap_columns(points: pd.DataFrame, train: pd.DataFrame, candidates: list[str],
                 tables: dict[int, pd.DataFrame], goal: str, cfg: Config) -> pd.DataFrame:
    """Per point: the LiftPath action, and for each trap method its action and lift row.

    The lift row is the method's action at the level that LiftPath uses for the point.
    """
    resolved = resolve_points(points, best_actions(tables, cfg))
    out = pd.DataFrame(index=points.index)
    out["liftpath_action"] = resolved["action"].where(resolved["status"] == RECOMMEND, None)
    recommenders = {"user_cf": make_user_cf(train, candidates, cfg),
                    "raw_success": make_raw_success(train, candidates, goal, cfg)}
    lifts = point_lifts(points, tables, cfg)
    for method, recommender in recommenders.items():
        chosen = pd.DataFrame({"row": np.arange(len(points)),
                               "action": recommender(points).to_numpy()})
        rows = chosen.merge(lifts, on=["row", "action"], how="left").sort_values("row")
        for col in TRAP_COLS:
            out[f"{method}_{col}"] = rows[col].to_numpy()
    out = out.astype({f"{m}_action": object for m in TRAP_METHODS})
    for method in TRAP_METHODS:
        col = f"{method}_action"
        out[col] = out[col].where(out[col].notna(), None)
    return out


def disagreement(liftpath: pd.Series, other: pd.Series) -> float:
    """Share of points where both give an action and the actions differ."""
    both = liftpath.notna() & other.notna()
    return float((liftpath[both] != other[both]).mean()) if both.any() else np.nan
