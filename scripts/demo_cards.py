"""Print 3 recommendation cards and 1 recovery card from the test data of the scope."""

import sys

import pandas as pd

from liftpath.config import load_config
from liftpath.lift import (
    ABSTAIN,
    NO_CLEAR_WINNER,
    RECOMMEND,
    best_actions,
    read_tables,
    resolve_points,
)
from liftpath.paths import scope_dir
from liftpath.recommend import State, label, recommend, recommend_points
from liftpath.recover import RECOVERY_LEVELS, explain_recovery

GOAL_NAMES = {"goal_pass": "pass", "goal_distinction": "distinction"}


def pick(points: pd.DataFrame, resolved: pd.DataFrame, status: str, seed: int,
         min_level: int = 0) -> pd.Series | None:
    match = resolved[(resolved["status"] == status)
                     & (resolved["level"].fillna(0) >= min_level)]
    if match.empty:
        return None
    return points.loc[match.sample(1, random_state=seed).index[0]]


def card(number: int, point: pd.Series, goal: str, tables: dict, cfg) -> str:
    state = State(point["module"], point["week_block"], point["score_band"],
                  point["effort_band"])
    rec = recommend(state, goal, tables, cfg)
    step = label(rec.estimate.action) if rec.estimate else "no change"
    return (f"Card {number}: student {point['student_id']}, {point['course_id']}, "
            f"week {point['week']}, goal: {GOAL_NAMES[goal]}\n"
            f"Status: {rec.status}. Next step: {step}.\n{rec.rationale}\n")


def main() -> int:
    cfg = load_config()
    folder = scope_dir(cfg)
    points = pd.read_parquet(folder / "decision_points.parquet")
    test = points[points["split"] == "test"]
    wanted = [("goal_pass", RECOMMEND, 0), ("goal_pass", NO_CLEAR_WINNER, 0),
              ("goal_distinction", RECOMMEND, 1)]
    number = 0
    for goal, status, min_level in wanted:
        tables = read_tables(folder / "lifts", goal)
        resolved = recommend_points(test, goal, tables, cfg)
        point = pick(test, resolved, status, cfg.seed, min_level)
        if point is None:
            point = pick(test, resolved, status, cfg.seed)
        if point is None:
            print(f"No test point has status {status} for {goal}.\n")
            continue
        number += 1
        print(card(number, point, goal, tables, cfg))

    recovery = pd.read_parquet(folder / "recovery_points.parquet")
    rtest = recovery[recovery["split"] == "test"]
    best = best_actions(read_tables(folder / "recovery", "goal_recover"), cfg, RECOVERY_LEVELS)
    resolved = resolve_points(rtest, best, RECOVERY_LEVELS)
    chosen = resolved[resolved["status"] != ABSTAIN]
    if chosen.empty:
        print("No recovery test point has a result.")
        return 0
    idx = chosen.sample(1, random_state=cfg.seed).index[0]
    point, rec = rtest.loc[idx], resolved.loc[idx]
    step = label(rec["action"]) if rec["status"] == RECOMMEND else "no change"
    print(f"Recovery card: student {point['student_id']}, {point['course_id']}, "
          f"assessment {point['assessment_id']} (score {point['score']:.0f})\n"
          f"Status: {rec['status']}. Go back to: {step}.\n"
          f"{explain_recovery(rec, point['module'], point['low_band'], cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
