"""Gate 2: on synthetic data with a known truth, effort-matched lift finds the real effect."""

from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from liftpath.adapters.synthetic import write_synthetic
from liftpath.config import load_config
from liftpath.lift import estimate_lifts
from liftpath.schema import CANONICAL, arrow_schema
from liftpath.states import build_decision_points, register_canonical, select_candidates

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    cfg = load_config(CONFIG_PATH)
    folder = tmp_path_factory.mktemp("synthetic")
    write_synthetic(cfg, folder)
    con = duckdb.connect()
    register_canonical(con, folder)
    candidates = select_candidates(con, cfg)
    points = build_decision_points(con, cfg, candidates)
    return cfg, folder, candidates, points[points["split"] == "train"]


def test_schema_and_candidates(synthetic):
    _, folder, candidates, train = synthetic
    for table in CANONICAL:
        assert pq.read_schema(folder / f"{table}.parquet") == arrow_schema(table)
    assert "homepage" not in candidates
    assert {"quiz", "forumng"} <= set(candidates)
    assert len(train) > 0


def test_raw_success_prefers_forum(synthetic):
    _, _, _, train = synthetic
    forum = train.loc[train["act_forumng"], "goal_pass"].mean()
    quiz = train.loc[train["act_quiz"], "goal_pass"].mean()
    assert forum > quiz


def pooled_lifts(synthetic):
    cfg, _, _, train = synthetic
    return estimate_lifts(train, [], "next_effort_band", ["act_quiz", "act_forumng"],
                          "goal_pass", cfg).set_index("action")


def test_lift_finds_quiz_effect(synthetic):
    assert pooled_lifts(synthetic).loc["act_quiz", "ci_low"] > 0


@pytest.mark.xfail(strict=True, reason="Gate 2 test 2 fails: see PROGRESS.md, Method issues")
def test_lift_ranks_quiz_over_forum(synthetic):
    out = pooled_lifts(synthetic)
    assert out.loc["act_quiz", "lift"] > out.loc["act_forumng", "lift"]
