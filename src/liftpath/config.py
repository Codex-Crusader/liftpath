"""Load config.yaml into a frozen Config. DATA_SCOPE overrides data_scope."""

import os
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

SCOPES = ("full", "sample", "synthetic")


@dataclass(frozen=True)
class Config:
    seed: int
    data_scope: str
    duckdb_memory_limit: str
    duckdb_threads: int
    n_candidates: int
    exclude_types: tuple[str, ...]
    use_fallback_groups: bool
    score_low_max: float
    score_mid_max: float
    min_count: int
    prior_strength: float
    display_min_count: int
    z: float
    n_boot: int
    low_score: float
    cf_neighbors: int
    gate_variety_min_share: float
    gate_variety_min_candidates: int
    gate_coverage_min: float
    app_students_per_course: int
    synthetic_students_per_presentation: int
    plan_horizon_weeks: int
    sim_worlds: tuple[str, ...]
    sim_cohorts: int
    sim_students_per_cohort: int
    sim_dev_cohorts: int
    sim_dev_students: int
    sim_compliance: float
    sim_explore_share: float
    sim_min_first_stage: float
    sim_boot: int
    rescue_min_count: int
    rescue_null_runs: int
    live_db_path: str
    trap_disagree_min: float
    scope: str  # data_scope after the DATA_SCOPE override


def load_config(path: Path = Path("config.yaml")) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    expected = {f.name for f in fields(Config)} - {"scope"}
    missing = expected - raw.keys()
    unknown = raw.keys() - expected
    if missing or unknown:
        raise ValueError(f"config keys: missing {sorted(missing)}, unknown {sorted(unknown)}")

    scope = os.environ.get("DATA_SCOPE") or raw["data_scope"]
    if scope not in SCOPES:
        raise ValueError(f"scope {scope!r} is not one of {SCOPES}")

    values = {**raw, "exclude_types": tuple(raw["exclude_types"]),
              "sim_worlds": tuple(raw["sim_worlds"]), "scope": scope}
    return Config(**values)
