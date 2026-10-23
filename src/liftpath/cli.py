"""Command line entry point: python -m liftpath.cli <step>."""

import argparse
import json
import runpy
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from liftpath.adapters.oulad import build_canonical
from liftpath.adapters.synthetic import write_synthetic
from liftpath.app_data import FIGURES, build_app_data
from liftpath.config import Config, load_config
from liftpath.db import connect
from liftpath.engine import ENGINE_COMMANDS, add_engine_parsers, run_engine
from liftpath.figures import sim_estimates_figure, sim_pass_rate_figure
from liftpath.lift import best_actions, lift_tables, resolve_points
from liftpath.paths import (
    APP_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    REPORTS_DIR,
    TMP_DIR,
    canonical_dir,
    scope_dir,
)
from liftpath.recover import RECOVERY_LEVELS, build_recovery_points, recovery_tables
from liftpath.report import run_eval
from liftpath.route import item_schedule, score_transitions
from liftpath.scopes import build_sample
from liftpath.sim import expected_results, run_world
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
    "plan",
    "sim",
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


def step_recover(cfg: Config) -> None:
    con = connect(cfg)
    register_canonical(con, canonical_dir(cfg))
    folder = scope_dir(cfg)
    candidates = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    points = build_recovery_points(con, cfg, candidates)
    points.to_parquet(folder / "recovery_points.parquet", index=False)
    print(f"recovery points: {points.shape}, by split: {points['split'].value_counts().to_dict()}")

    out = folder / "recovery"
    out.mkdir(exist_ok=True)
    tables = recovery_tables(points[points["split"] == "train"], candidates, cfg)
    best = best_actions(tables, cfg, RECOVERY_LEVELS)
    for level in tables:
        tables[level].to_parquet(out / f"goal_recover_level{level}.parquet", index=False)
        best[level].to_parquet(out / f"best_goal_recover_level{level}.parquet", index=False)
    test = points[points["split"] == "test"]
    shares = resolve_points(test, best, RECOVERY_LEVELS)["status"].value_counts(normalize=True)
    print(f"goal_recover: test status shares {shares.round(3).to_dict()}")


def step_eval(cfg: Config) -> None:
    output = run_eval(cfg)
    for goal, result in output["goals"].items():
        for row in result["results"]:
            print(f"{goal} {row['name']}: coverage {row['coverage']:.3f}, lift {row['lift']:+.4f}"
                  f", net {row['net_lift']:+.4f} [{row['net_ci_low']:+.4f}, "
                  f"{row['net_ci_high']:+.4f}]")
    gate3 = output["gate3"]
    print(f"Gate 3: coverage {gate3['coverage_not_abstain']:.3f}, "
          f"{'PASS' if gate3['passes'] else 'FAIL'}")


def step_app_data(cfg: Config) -> None:
    folder = scope_dir(cfg)
    suffix = "" if cfg.scope == "full" else f"_{cfg.scope}"
    eval_path = REPORTS_DIR / f"eval_results{suffix}.json"
    fairness_path = REPORTS_DIR / f"fairness_results{suffix}.json"
    figures = {name: REPORTS_DIR / "figures" / name.replace(".png", f"{suffix}.png")
               for name in FIGURES}
    figures["synthetic_truth.png"] = REPORTS_DIR / "figures" / "synthetic_truth.png"
    out = APP_DIR if cfg.scope == "full" else TMP_DIR / f"app_{cfg.scope}"
    sizes = build_app_data(
        cfg,
        points=pd.read_parquet(folder / "decision_points.parquet"),
        candidates=json.loads((folder / "candidates.json").read_text(encoding="utf-8")),
        recovery_points=pd.read_parquet(folder / "recovery_points.parquet"),
        eval_results=(json.loads(eval_path.read_text(encoding="utf-8"))
                      if eval_path.exists() else None),
        fairness=pd.read_json(fairness_path) if fairness_path.exists() else None,
        figures=figures,
        out_dir=out,
    )
    total = sum(sizes.values())
    print(f"{out.as_posix()}: {len(sizes)} files, {total / 1e6:.2f} MB")


def step_plan(cfg: Config) -> None:
    folder = scope_dir(cfg)
    points = pd.read_parquet(folder / "decision_points.parquet")
    candidates = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    out = folder / "plan"
    out.mkdir(exist_ok=True)
    transitions = score_transitions(points[points["split"] == "train"], candidates, cfg)
    transitions.to_parquet(out / "transitions.parquet", index=False)
    con = connect(cfg)
    register_canonical(con, canonical_dir(cfg))
    schedule = item_schedule(con, cfg)
    schedule.to_parquet(out / "schedule.parquet", index=False)
    print(f"transitions: {transitions.shape}, schedule: {schedule.shape}")


def step_sim(cfg: Config) -> None:
    start = time.time()
    out = PROCESSED_DIR / "synthetic" / "sim"
    out.mkdir(parents=True, exist_ok=True)
    results, estimates = [], []
    for world in cfg.sim_worlds:
        res, est = run_world(world, cfg, cfg.sim_students_per_cohort, cfg.sim_cohorts)
        results.append(res)
        estimates.append(est)
        print(f"{world}: done after {time.time() - start:.0f} s")
    results = pd.concat(results, ignore_index=True)
    estimates = pd.concat(estimates, ignore_index=True)
    results.to_parquet(out / "results.parquet", index=False)
    estimates.to_parquet(out / "estimates.parquet", index=False)
    figures = REPORTS_DIR / "figures"
    for world, name, title in (("standard", "standard", "standard world"),
                               ("hidden_confounder", "hidden", "hidden confounder world")):
        sim_pass_rate_figure(results[results["world"] == world], title,
                             figures / f"sim_pass_rate_{name}.png")
    sim_estimates_figure(estimates[estimates["world"] == "hidden_confounder"],
                         figures / "sim_estimates_hidden.png")
    last = results["cohort"].max()
    final = results[results["cohort"] == last].pivot(index="policy", columns="world",
                                                       values="pass_rate")
    print(f"final cohort pass rate:\n{final.round(3).to_string()}")
    for key, value in expected_results(results).items():
        print(f"{key}: {round(value, 3) if isinstance(value, float) else value}")
    print(f"sim runtime: {time.time() - start:.0f} s")


def not_built(cfg: Config) -> None:
    print("not built yet")


HANDLERS = {
    "data": step_data,
    "sample": step_sample,
    "profile": step_profile,
    "synthetic": step_synthetic,
    "states": step_states,
    "lifts": step_lifts,
    "recover": step_recover,
    "eval": step_eval,
    "app-data": step_app_data,
    "plan": step_plan,
    "sim": step_sim,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="liftpath")
    sub = parser.add_subparsers(dest="step", required=True)
    for step in STEPS:
        sub.add_parser(step)
    add_engine_parsers(sub)
    args = parser.parse_args(argv)
    if args.step in ENGINE_COMMANDS:
        run_engine(args, load_config())
        return
    HANDLERS.get(args.step, not_built)(load_config())


if __name__ == "__main__":
    main()
