from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from liftpath.baselines import make_random
from liftpath.config import load_config
from liftpath.evaluate import evaluate_all, follower_lift

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CELL = {"module": "AAA", "week_block": "early", "score_band": "mid", "effort_band": "mid"}


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    return load_config(CONFIG_PATH)


def points_and_actions():
    rows, actions = [], []

    def add(next_band, action, act_x, act_y, goals):
        for g in goals:
            rows.append({**CELL, "course_id": "C", "student_id": len(rows),
                         "next_effort_band": next_band, "act_x": act_x, "act_y": act_y,
                         "goal": bool(g)})
            actions.append(action)

    # Stratum low: 4 followers (3 reach the goal), 4 non-followers (1 reaches it).
    add("low", "x", True, False, [1, 1])
    add("low", "y", False, True, [1, 0])
    add("low", "x", False, True, [1, 0, 0, 0])   # act_y does not make them followers of x
    # Stratum high: 2 followers (2 reach it), 6 non-followers (2 reach it).
    add("high", "y", False, True, [1, 1])
    add("high", "y", True, False, [1, 1, 0, 0, 0, 0])
    # Not used: only followers, next effort none, and no action.
    add("mid", "x", True, False, [0, 0])
    add("none", "x", True, False, [1, 1])
    add("low", None, True, True, [0, 0, 0])
    return pd.DataFrame(rows), pd.Series(actions, dtype=object)


def test_follower_lift_known_answer(cfg):
    points, actions = points_and_actions()
    result = follower_lift(points, actions, "goal", cfg, np.random.default_rng(0))
    w_low, w_high = 4 * 4 / 8, 2 * 6 / 8
    expected = (w_low * (3 / 4 - 1 / 4) + w_high * (2 / 2 - 2 / 6)) / (w_low + w_high)
    assert result.lift == pytest.approx(expected, abs=1e-12)
    assert result.n_points == len(points) - 3
    assert result.ci_low <= result.lift <= result.ci_high


def random_points(n_students: int, seed: int) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    act = rng.random(n_students) < 0.5
    goal = rng.random(n_students) < np.where(act, 0.6, 0.4)
    points = pd.DataFrame({**CELL, "course_id": "C", "student_id": np.arange(n_students),
                           "next_effort_band": rng.choice(["low", "high"], n_students),
                           "act_x": act, "goal": goal})
    return points, pd.Series("x", index=points.index, dtype=object)


def test_bootstrap_resamples_students_not_rows(cfg):
    points, actions = random_points(300, seed=1)
    repeated = points.loc[points.index.repeat(5)].reset_index(drop=True)
    once = follower_lift(points, actions, "goal", cfg, np.random.default_rng(9))
    five = follower_lift(repeated, pd.Series("x", index=repeated.index, dtype=object),
                         "goal", cfg, np.random.default_rng(9))
    # Repeating each student's rows must not narrow a student-level interval.
    assert five.lift == pytest.approx(once.lift, abs=1e-12)
    assert (five.ci_low, five.ci_high) == pytest.approx((once.ci_low, once.ci_high), abs=1e-12)
    assert once.ci_high - once.ci_low > 0


def test_evaluate_all_net_lift(cfg):
    points, _ = random_points(400, seed=2)
    recs = {"random": make_random(["x"], cfg.seed),
            "none_half": lambda p: pd.Series(np.where(p.index % 2 == 0, "x", None),
                                             index=p.index, dtype=object)}
    table = evaluate_all(points, recs, "goal", cfg).set_index("name")
    assert table.loc["random", "net_lift"] == 0
    assert table.loc["random", "coverage"] == 1
    assert table.loc["none_half", "coverage"] == pytest.approx(0.5)
    assert table.loc["none_half", "common_n_points"] == 200
    assert table.loc["none_half", "net_ci_low"] <= table.loc["none_half", "net_lift"]
