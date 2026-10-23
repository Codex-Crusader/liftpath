"""Engine commands (BUILD2 Phase D): `liftpath recommend` and `liftpath route` as JSON."""

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.live import CUTOFF_FILE, cutoff_row, live_tables_exist, load_lift_tables
from liftpath.paths import APP_DIR
from liftpath.recommend import State, label, recommend
from liftpath.route import ITEM_NOTE, PROJECTION_NOTE, plan_route, table_projector

GOAL_ARGS = {"pass": "goal_pass", "distinction": "goal_distinction"}
SCORE_BANDS = ("none", "low", "mid", "high")
EFFORT_BANDS = ("none", "low", "mid", "high")
ENGINE_COMMANDS = ("recommend", "route")


def add_engine_parsers(sub: argparse._SubParsersAction) -> None:
    for name in ENGINE_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--module", required=True)
        p.add_argument("--week", type=int, required=True)
        p.add_argument("--score-band", choices=SCORE_BANDS, required=True)
        p.add_argument("--effort-band", choices=EFFORT_BANDS, required=True)
        p.add_argument("--goal", choices=list(GOAL_ARGS), default="pass")
        p.add_argument("--json", action="store_true", help="print JSON")


def json_ready(value):
    """Plain Python values for strict JSON: NaN and NA become null."""
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [json_ready(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if value is pd.NA or value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def dumps(payload: dict) -> str:
    return json.dumps(json_ready(payload), indent=2, allow_nan=False)


def engine_state(args: argparse.Namespace) -> tuple[State, str]:
    cutoffs = pd.read_parquet(APP_DIR / CUTOFF_FILE)
    block = cutoff_row(cutoffs, args.module, args.week)["week_block"]
    return State(args.module, block, args.score_band, args.effort_band), GOAL_ARGS[args.goal]


def tables_source(goal: str) -> str:
    return "live" if live_tables_exist(goal) else "app"


def recommend_payload(args: argparse.Namespace, cfg: Config) -> dict:
    state, goal = engine_state(args)
    rec = recommend(state, goal, load_lift_tables(goal), cfg)
    e = rec.estimate
    return {"state": {**asdict(state), "week": args.week}, "goal": goal, "status": rec.status,
            "action": e.action if e else None, "label": label(e.action) if e else None,
            "lift": e.lift if e else None, "ci_low": e.ci_low if e else None,
            "ci_high": e.ci_high if e else None, "level": e.level if e else None,
            "rationale": rec.rationale, "tables": tables_source(goal)}


def app_plan(app_dir: Path = APP_DIR):
    """The route lookups and the item schedule from the app data (SPEC 19 safe copies)."""
    paths = [app_dir / f"plan_{n}.parquet" for n in ("projections", "goal_rates", "schedule")]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise ValueError(f"No route data in {app_dir} ({', '.join(missing)}). "
                         "Run make plan and then make app-data.")
    projections, rates, schedule = (pd.read_parquet(p) for p in paths)
    return table_projector(projections, rates), schedule


def latest_course(schedule: pd.DataFrame, module: str) -> str | None:
    """The latest presentation of the module in the item schedule (for the item lists)."""
    courses = sorted(c for c in schedule["course_id"].unique() if c.startswith(f"{module}_"))
    return courses[-1] if courses else None


def route_payload(args: argparse.Namespace, cfg: Config) -> dict:
    state, goal = engine_state(args)
    projector, schedule = app_plan()
    course_id = latest_course(schedule, args.module)
    point = pd.Series({**asdict(state), "week": args.week, "course_id": course_id})
    route = plan_route(point, goal, load_lift_tables(goal), projector, schedule, cfg)
    return {"state": {**asdict(state), "week": args.week}, "goal": goal,
            "course_id": course_id, "effort": route.effort,
            "steps": [asdict(step) for step in route.steps],
            "projected_route": route.projected_route,
            "projected_typical": route.projected_typical,
            "projection_note": PROJECTION_NOTE, "item_note": ITEM_NOTE,
            "stop_reason": route.stop_reason, "tables": tables_source(goal)}


def route_text(payload: dict) -> str:
    lines = [f"Week {s['week']}: {s['label']}" for s in payload["steps"]]
    for key, name in (("projected_route", "route"), ("projected_typical", "typical path")):
        value = payload[key]
        if value is not None:
            lines.append(f"Projected rate, {name}: {value:.0%}. {PROJECTION_NOTE}")
    return "\n".join([*lines, payload["stop_reason"]])


def run_engine(args: argparse.Namespace, cfg: Config) -> None:
    try:
        payload = (recommend_payload if args.step == "recommend" else route_payload)(args, cfg)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
    if args.json:
        print(dumps(payload))
    elif args.step == "recommend":
        print(payload["rationale"])
    else:
        print(route_text(json_ready(payload)))
