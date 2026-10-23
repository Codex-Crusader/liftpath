"""Command line entry point: python -m liftpath.cli <step>."""

import argparse
import json
import runpy
from dataclasses import replace
from pathlib import Path

import pandas as pd

from liftpath.adapters.oulad import build_canonical
from liftpath.adapters.synthetic import write_synthetic
from liftpath.config import Config, load_config
from liftpath.db import connect
from liftpath.lift import best_actions, lift_tables, resolve_points
from liftpath.paths import RAW_DIR, REPORTS_DIR, canonical_dir, scope_dir
from liftpath.scopes import build_sample
from liftpath.states import (
    build_decision_points,
    check_variety,
    gate1_passes,
    register_canonical,
    select_candidates,
    single_presentation_modules,
    variety_report,
)

SCRIPTS_DIR = Path("scripts")
GOALS = ("goal_pass", "goal_distinction")

STEPS = (
    "data",
    "sample",
    "synthetic",
    "profile",
    "states",
    "lifts",
    "recover",
    "eval",
    "app-data",
)


def run_script(name: str) -> None:
    code = runpy.run_path(str(SCRIPTS_DIR / name))["main"]()
    if code:
        raise SystemExit(code)


def step_data(cfg: Config) -> None:
    run_script("download_oulad.py")
    full = replace(cfg, scope="full")
    stats = build_canonical(connect(full), RAW_DIR, canonical_dir(full))
    for key, value in stats.items():
        print(f"{key}: {value:,}")


def step_sample(cfg: Config) -> None:
    stats = build_sample(connect(cfg), cfg)
    for key, value in stats.items():
        print(f"{key}: {value}")


def step_profile(cfg: Config) -> None:
    run_script("profile_data.py")


def step_states(cfg: Config) -> None:
    con = connect(cfg)
    register_canonical(con, canonical_dir(cfg))
    for module in single_presentation_modules(con):
        print(f"module {module} has one presentation: train only")
    candidates = select_candidates(con, cfg)
    points = build_decision_points(con, cfg, candidates)
    out = scope_dir(cfg)
    points.to_parquet(out / "decision_points.parquet", index=False)
    (out / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    print(f"candidates: {candidates}")
    print(f"decision points: {points.shape}, by split: {points['split'].value_counts().to_dict()}")

    variety = check_variety(points, candidates, cfg)
    suffix = "" if cfg.scope == "full" else f"_{cfg.scope}"
    report = REPORTS_DIR / f"gate1_variety{suffix}.md"
    REPORTS_DIR.mkdir(exist_ok=True)
    n_train = int((points["split"] == "train").sum())
    report.write_text(variety_report(variety, cfg, n_train), encoding="utf-8")
    print(f"{report.as_posix()}: Gate 1 {'PASS' if gate1_passes(variety, cfg) else 'FAIL'}")


def step_synthetic(cfg: Config) -> None:
    syn = replace(cfg, scope="synthetic")
    for table, rows in write_synthetic(syn, canonical_dir(syn)).items():
        print(f"{table}: {rows:,}")


def step_lifts(cfg: Config) -> None:
    folder = scope_dir(cfg)
    points = pd.read_parquet(folder / "decision_points.parquet")
    candidates = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    train, test = points[points["split"] == "train"], points[points["split"] == "test"]
    out = folder / "lifts"
    out.mkdir(exist_ok=True)
    for goal in GOALS:
        tables = lift_tables(train, candidates, goal, cfg)
        best = best_actions(tables, cfg)
        for level in tables:
            tables[level].to_parquet(out / f"{goal}_level{level}.parquet", index=False)
            best[level].to_parquet(out / f"best_{goal}_level{level}.parquet", index=False)
        rows = {level: len(table) for level, table in tables.items()}
        shares = resolve_points(test, best)["status"].value_counts(normalize=True).round(3)
        print(f"{goal}: lift rows per level {rows}, test status shares {shares.to_dict()}")


def not_built(cfg: Config) -> None:
    print("not built yet")


HANDLERS = {
    "data": step_data,
    "sample": step_sample,
    "profile": step_profile,
    "synthetic": step_synthetic,
    "states": step_states,
    "lifts": step_lifts,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="liftpath")
    sub = parser.add_subparsers(dest="step", required=True)
    for step in STEPS:
        sub.add_parser(step)
    args = parser.parse_args(argv)
    HANDLERS.get(args.step, not_built)(load_config())


if __name__ == "__main__":
    main()
