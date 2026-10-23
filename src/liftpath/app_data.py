"""make app-data: small, suppressed files for the Streamlit app (SPEC sections 12 and 19).

Student rows keep only the state columns and the recommendations. They have no outcomes,
no activity flags and no other identifiers.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import (
    ESTIMATE_COLS,
    LEVELS,
    STUDENT_KEY,
    band_table,
    best_actions,
    lift_tables,
    resolve_points,
)
from liftpath.live import CUTOFF_FILE, effort_cutoffs
from liftpath.privacy import suppress_counts
from liftpath.recover import RECOVERY_LEVELS, recovery_tables
from liftpath.trap import TRAP_COLS, TRAP_METHODS, trap_columns

GOALS = ("goal_pass", "goal_distinction")
STATE_COLS = ["course_id", "module", "presentation", "student_id", "week", "week_block",
              "score_band", "effort_band"]
LIFT_COUNTS = ["n_did", "n_did_not"]
AUDIT_COUNTS = ["n1", "k1", "u1", "n0", "k0", "u0"]
RECOVERY_COLS = ["course_id", "module", "student_id", "assessment_id", "score", "low_band"]
FIGURES = ("eval_lift.png", "fairness.png", "synthetic_truth.png")
EVAL_COUNT_KEYS = ("n_points", "common_n_points")
CONFIG_KEYS = ("min_count", "display_min_count", "prior_strength", "z", "low_score")


def write(df: pd.DataFrame, path: Path) -> None:
    df.reset_index(drop=True).to_parquet(path, index=False)


def sample_students(test: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Up to app_students_per_course test students per course_id, seeded. All columns."""
    keys = test[STUDENT_KEY].drop_duplicates()
    rng = np.random.default_rng(cfg.seed)
    keys = keys.assign(_order=rng.random(len(keys))).sort_values("_order")
    chosen = keys.groupby("course_id").head(cfg.app_students_per_course)[STUDENT_KEY]
    return test.merge(chosen, on=STUDENT_KEY)


def audit_table(train: pd.DataFrame, candidates: list[str], goal: str, cfg: Config):
    """Level 0 band details for the teacher audit. Rates are hidden where a count is."""
    bands = band_table(train, LEVELS[0], "next_effort_band", [f"act_{a}" for a in candidates],
                       goal, cfg).drop(columns=["w", "var"])
    bands["action"] = bands["action"].str.removeprefix("act_")
    bands = suppress_counts(bands, AUDIT_COUNTS, cfg)
    bands.loc[bands["suppressed"], ["p1", "p0"]] = np.nan
    return bands


def suppress_eval(results: dict, cfg: Config) -> dict:
    """Hide any point count below display_min_count in the eval results."""
    for goal in results.get("goals", {}).values():
        goal["common_n_points"] = (None if goal["common_n_points"] < cfg.display_min_count
                                   else goal["common_n_points"])
        for row in goal["results"]:
            for key in EVAL_COUNT_KEYS:
                if key in row and row[key] < cfg.display_min_count:
                    row[key] = None
    return results


def build_app_data(cfg: Config, points: pd.DataFrame, candidates: list[str],
                   recovery_points: pd.DataFrame, eval_results: dict | None,
                   fairness: pd.DataFrame | None, figures: dict[str, Path],
                   out_dir: Path, rescue_dir: Path | None = None) -> dict[str, int]:
    """Write the app files to out_dir. Return the size in bytes of each file."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "figures").mkdir(parents=True)
    train, test = points[points["split"] == "train"], points[points["split"] == "test"]

    # The baselines need the full state rows. The app file keeps only STATE_COLS.
    sample = sample_students(test, cfg)
    students = sample[STATE_COLS].copy()
    for goal in GOALS:
        tables = lift_tables(train, candidates, goal, cfg)
        best = best_actions(tables, cfg)
        resolved = resolve_points(students, best)
        students[f"{goal}_status"] = resolved["status"]
        students[f"{goal}_action"] = resolved["action"]
        students[f"{goal}_level"] = resolved["level"]
        trap = trap_columns(sample, train, candidates, tables, goal, cfg)
        for method in TRAP_METHODS:
            for col in TRAP_COLS:
                students[f"{goal}_{method}_{col}"] = trap[f"{method}_{col}"]
        for level, table in tables.items():
            write(suppress_counts(table, LIFT_COUNTS, cfg),
                  out_dir / f"{goal}_level{level}.parquet")
            write(suppress_counts(best[level], LIFT_COUNTS, cfg),
                  out_dir / f"best_{goal}_level{level}.parquet")
        write(audit_table(train, candidates, goal, cfg), out_dir / f"audit_{goal}.parquet")
    write(students, out_dir / "students.parquet")
    write(effort_cutoffs(train), out_dir / CUTOFF_FILE)

    rtrain = recovery_points[recovery_points["split"] == "train"]
    rtest = recovery_points[recovery_points["split"] == "test"][RECOVERY_COLS].copy()
    rtables = recovery_tables(rtrain, candidates, cfg)
    resolved = resolve_points(rtest, best_actions(rtables, cfg, RECOVERY_LEVELS),
                              RECOVERY_LEVELS)
    rtest = pd.concat([rtest, resolved[["status", "action", "level", *ESTIMATE_COLS]]], axis=1)
    write(suppress_counts(rtest, LIFT_COUNTS, cfg), out_dir / "recovery_points.parquet")
    for level, table in rtables.items():
        write(suppress_counts(table, LIFT_COUNTS, cfg),
              out_dir / f"goal_recover_level{level}.parquet")

    if rescue_dir is not None and (rescue_dir / "edges.parquet").exists():
        edges = pd.read_parquet(rescue_dir / "edges.parquet")
        write(suppress_counts(edges, LIFT_COUNTS, cfg), out_dir / "rescue_edges.parquet")
        items = pd.read_parquet(rescue_dir / "items.parquet")
        write(suppress_counts(items, ["n_students"], cfg), out_dir / "rescue_items.parquet")
        shutil.copy2(rescue_dir / "meta.json", out_dir / "rescue_meta.json")

    if eval_results is not None:
        (out_dir / "eval_results.json").write_text(
            json.dumps(suppress_eval(eval_results, cfg), indent=2), encoding="utf-8")
    if fairness is not None:
        write(suppress_counts(fairness, ["n_students", "n_points"], cfg),
              out_dir / "fairness.parquet")
    for name, source in figures.items():
        if source.exists():
            shutil.copy2(source, out_dir / "figures" / name)

    meta = {"scope": cfg.scope, "candidates": candidates, "goals": list(GOALS),
            "config": {k: getattr(cfg, k) for k in CONFIG_KEYS},
            "students": int(students[STUDENT_KEY].drop_duplicates().shape[0])}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {p.relative_to(out_dir).as_posix(): p.stat().st_size
            for p in sorted(out_dir.rglob("*")) if p.is_file()}
