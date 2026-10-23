"""Route planning (BUILD2 Phase A): hand example, abstain stop, no outcome use in items."""

import shutil
from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from liftpath.adapters.synthetic import write_synthetic
from liftpath.config import load_config
from liftpath.lift import ABSTAIN, LEVELS, lift_tables
from liftpath.route import (
    KEEP,
    goal_rate,
    item_schedule,
    plan_route,
    project,
    score_transitions,
)
from liftpath.states import build_decision_points, register_canonical, select_candidates

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
TABLE_COLS = ["action", "lift", "se", "ci_low", "ci_high", "p1_avg", "p0_avg", "n_did",
              "n_did_not", "base_rate"]


def hand_points() -> pd.DataFrame:
    """10 students at week 0 (low scores). Students 0 to 3 use quizzes and reach mid scores
    at week 1. The others stay low. Pass: students 0, 1, 2 and 4."""
    ids = np.arange(10)
    quiz = ids < 4
    passed = np.isin(ids, [0, 1, 2, 4])
    base = {"course_id": "M_2013J", "module": "M", "presentation": "2013J",
            "split": "train", "week_block": "early", "effort_band": "mid",
            "next_effort_band": "mid", "act_forumng": False}
    week0 = pd.DataFrame({**base, "student_id": ids, "week": 0, "score_band": "low",
                          "act_quiz": quiz, "goal_pass": passed, "goal_distinction": False})
    week1 = pd.DataFrame({**base, "student_id": ids, "week": 1,
                          "score_band": np.where(quiz, "mid", "low"), "act_quiz": False,
                          "goal_pass": passed, "goal_distinction": False})
    return pd.concat([week0, week1], ignore_index=True)


def hand_tables(cfg) -> dict[int, pd.DataFrame]:
    """One level 0 row: quiz helps at (M, early, low, mid). Nothing else has data."""
    row = {"module": "M", "week_block": "early", "score_band": "low", "effort_band": "mid",
           "action": "quiz", "lift": 0.1, "se": 0.02, "ci_low": 0.06, "ci_high": 0.14,
           "p1_avg": 0.6, "p0_avg": 0.5, "n_did": 100, "n_did_not": 100, "base_rate": 0.5}
    tables = {level: pd.DataFrame(columns=[*cells, *TABLE_COLS])
              for level, cells in LEVELS.items()}
    tables[0] = pd.DataFrame([row])
    return tables


@pytest.fixture
def hand():
    cfg = replace(load_config(CONFIG_PATH), min_count=2, plan_horizon_weeks=1)
    points = hand_points()
    transitions = score_transitions(points, ["quiz", "forumng"], cfg)
    schedule = pd.DataFrame(columns=["course_id", "item_id", "item_type", "action",
                                     "active_day", "active_week", "clicks"])
    return cfg, points, transitions, schedule


def test_projection_by_hand(hand):
    cfg, _, transitions, _ = hand
    # Quiz users move to mid (4 of 4). All students: 6 stay low, 4 move to mid.
    assert project(transitions, "M", 0, "low", "mid", "quiz", cfg)[1:] == ("mid", 0)
    assert project(transitions, "M", 0, "low", "mid", KEEP, cfg)[1:] == ("low", 0)

    m = cfg.prior_strength
    prior = 4 / 10
    route_rate = (3 + m * prior) / (4 + m)    # mid at week 1: students 0 to 3, 3 passed
    typical_rate = (1 + m * prior) / (6 + m)  # low at week 1: students 4 to 9, 1 passed
    assert goal_rate(transitions, "M", 1, "mid", "mid", "goal_pass", cfg) == pytest.approx(
        route_rate)

    route = plan_route(hand_points().iloc[0], "goal_pass", hand_tables(cfg), transitions,
                       hand[3], cfg)
    assert [s.action for s in route.steps] == ["quiz"]
    assert route.projected_route == pytest.approx(route_rate)
    assert route.projected_typical == pytest.approx(typical_rate)
    assert route.projected_route != route.projected_typical


def test_route_stops_on_abstain(hand):
    cfg, points, transitions, schedule = hand
    cfg = replace(cfg, plan_horizon_weeks=3)
    route = plan_route(points.iloc[0], "goal_pass", hand_tables(cfg), transitions, schedule,
                       cfg)
    # Week 0 recommends quiz. The projected week 1 state (mid scores) has no data.
    assert len(route.steps) == 1
    assert "Not enough similar students" in route.stop_reason
    empty = {level: t.iloc[0:0] for level, t in hand_tables(cfg).items()}
    no_route = plan_route(points.iloc[0], "goal_pass", empty, transitions, schedule, cfg)
    assert no_route.steps == () and np.isnan(no_route.projected_route)
    assert ABSTAIN not in [s.status for s in route.steps]


def build(folder: Path, cfg):
    con = duckdb.connect()
    register_canonical(con, folder)
    candidates = select_candidates(con, cfg)
    points = build_decision_points(con, cfg, candidates)
    return points, candidates, item_schedule(con, cfg)


def test_items_ignore_outcomes(tmp_path):
    cfg = load_config(CONFIG_PATH)
    original = tmp_path / "original"
    write_synthetic(cfg, original)
    shuffled = tmp_path / "shuffled"
    shutil.copytree(original, shuffled)
    table = pq.read_table(shuffled / "enrollments.parquet")
    results = table.column("final_result").to_numpy(zero_copy_only=False)
    permuted = np.random.default_rng(cfg.seed).permutation(results)
    table = table.set_column(table.schema.get_field_index("final_result"),
                             table.schema.field("final_result"),
                             pa.array(permuted, type=table.schema.field("final_result").type))
    pq.write_table(table, shuffled / "enrollments.parquet")

    points, candidates, schedule = build(original, cfg)
    points_s, _, schedule_s = build(shuffled, cfg)
    assert not points["goal_pass"].equals(points_s["goal_pass"])
    pd.testing.assert_frame_equal(schedule, schedule_s)

    # The lift tables stay fixed. Only the transitions see the shuffled goals.
    train = points[points["split"] == "train"]
    tables = lift_tables(train, candidates, "goal_pass", cfg)
    transitions = score_transitions(train, candidates, cfg)
    transitions_s = score_transitions(points_s[points_s["split"] == "train"], candidates, cfg)
    test = points[points["split"] == "test"].sample(20, random_state=cfg.seed)
    with_items = 0
    for _, point in test.iterrows():
        a = plan_route(point, "goal_pass", tables, transitions, schedule, cfg)
        b = plan_route(point, "goal_pass", tables, transitions_s, schedule_s, cfg)
        assert [(s.action, s.items) for s in a.steps] == [(s.action, s.items) for s in b.steps]
        with_items += any(s.items for s in a.steps)
    assert with_items > 0
