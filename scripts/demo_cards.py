"""Print 3 recommendation cards, 1 recovery card and 2 routes from the test data of the scope."""

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
from liftpath.recover import RECOVERY_LEVELS, WEEK_DAYS, explain_recovery
from liftpath.route import ITEM_NOTE, PROJECTION_NOTE, plan_route, rescue_card

GOAL_NAMES = {"goal_pass": "pass", "goal_distinction": "distinction"}
ROUTES = 2
ROUTE_TRIES = 200


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
          f"{explain_recovery(rec, point['module'], point['low_band'], cfg)}\n")
    resolved_points = pd.concat(
        [rtest, resolved.drop(columns=rtest.columns, errors="ignore")], axis=1)
    print_routes(test, resolved_points, folder, cfg)
    return 0


def full_route(route) -> bool:
    return (len(route.steps) > 0 and route.stop_reason.startswith("The route reached")
            and any(s.status == RECOMMEND and s.items for s in route.steps))


def print_routes(test: pd.DataFrame, recovery: pd.DataFrame, folder, cfg) -> None:
    """Print ROUTES routes that reach the horizon and have a recommend step with items."""
    transitions = pd.read_parquet(folder / "plan" / "transitions.parquet")
    schedule = pd.read_parquet(folder / "plan" / "schedule.parquet")
    goal = "goal_pass"
    tables = read_tables(folder / "lifts", goal)
    # Points inside the window of a rescue recommendation come first, so the demo also
    # shows a rescue card.
    rescue = recovery.loc[recovery["status"] == RECOMMEND,
                          ["course_id", "student_id", "due_day", "next_due_day"]]
    rescued = test.merge(rescue, on=["course_id", "student_id"])
    week_end = WEEK_DAYS * rescued["week"] + WEEK_DAYS - 1
    rescued = rescued[(rescued["due_day"] <= week_end) & (week_end < rescued["next_due_day"])]
    rescued = rescued.drop(columns=["due_day", "next_due_day"])
    pool = pd.concat([rescued.sample(frac=1, random_state=cfg.seed),
                      test.sample(ROUTE_TRIES, random_state=cfg.seed)]).head(ROUTE_TRIES)
    shown = 0
    for _, point in pool.iterrows():
        route = plan_route(point, goal, tables, transitions, schedule, cfg)
        if not full_route(route):
            continue
        shown += 1
        print(f"Route {shown}: student {point['student_id']}, {point['course_id']}, "
              f"week {point['week']}, goal: {GOAL_NAMES[goal]}, plan effort: {route.effort}")
        rescue = rescue_card(point, recovery, schedule, cfg)
        if rescue is not None:
            print(f"  Rescue: after a score of {rescue.score:.0f} on assessment "
                  f"{rescue.assessment_id}, go back to {rescue.label}. "
                  f"Items: {list(rescue.items)}.\n  {rescue.rationale}")
        for s in route.steps:
            lift = (f", lift {s.lift:+.1%} (95% range {s.ci_low:+.1%} to {s.ci_high:+.1%})"
                    if s.lift is not None else "")
            items = f", items {list(s.items)}" if s.items else ""
            print(f"  Week {s.week} ({s.score_band} scores): {s.label}{lift}{items}")
        print(f"  Projected pass rate: route {route.projected_route:.1%}, typical "
              f"{route.projected_typical:.1%}. {PROJECTION_NOTE}\n  {ITEM_NOTE}\n"
              f"  {route.stop_reason}\n")
        if shown == ROUTES:
            return
    print(f"Only {shown} of {ROUTES} routes reach the horizon in {ROUTE_TRIES} tries.")


if __name__ == "__main__":
    sys.exit(main())
