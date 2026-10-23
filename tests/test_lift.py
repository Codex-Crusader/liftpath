import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.lift import (
    ABSTAIN,
    LEVELS,
    NO_CLEAR_WINNER,
    RECOMMEND,
    best_actions,
    estimate_lifts,
    resolve_points,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    return load_config(CONFIG_PATH)


def group(band, act, goals, students):
    return [{"course_id": "C", "student_id": s, "effort": band, "act_x": act, "goal": bool(g)}
            for g, s in zip(goals, students, strict=True)]


def hand_points() -> pd.DataFrame:
    rows = (
        group("low", True, [1, 1, 1, 0], [1, 1, 2, 2])          # n1=4, k1=3, u1=2
        + group("low", False, [1, 1, 0, 0, 0, 0], range(3, 9))  # n0=6, k0=2, u0=6
        + group("mid", False, [1, 1], [9, 10])                  # n1=0: band not used
        + group("high", True, [1, 1, 1, 1, 0], range(11, 16))   # n1=5, k1=4, u1=5
        + group("high", False, [1, 1, 0, 0, 0], range(16, 21))  # n0=5, k0=2, u0=5
        + group("none", False, [0, 0], [21, 22])                # effort none: not compared
    )
    return pd.DataFrame(rows)


def test_hand_example(cfg):
    out = estimate_lifts(hand_points(), [], "effort", ["act_x"], "goal", cfg)
    assert len(out) == 1
    row = out.iloc[0]

    m, z = 10, 1.96
    p_c = 13 / 24
    p1_low, p0_low = (3 + m * p_c) / (4 + m), (2 + m * p_c) / (6 + m)
    p1_high, p0_high = (4 + m * p_c) / (5 + m), (2 + m * p_c) / (5 + m)
    w_low, w_high = 4 * 6 / 10, 5 * 5 / 10
    var_low = p1_low * (1 - p1_low) / (2 + m) + p0_low * (1 - p0_low) / (6 + m)
    var_high = p1_high * (1 - p1_high) / (5 + m) + p0_high * (1 - p0_high) / (5 + m)
    sum_w = w_low + w_high
    lift = (w_low * (p1_low - p0_low) + w_high * (p1_high - p0_high)) / sum_w
    se = math.sqrt(w_low**2 * var_low + w_high**2 * var_high) / sum_w

    assert row["base_rate"] == pytest.approx(p_c, abs=1e-9)
    assert row["lift"] == pytest.approx(lift, abs=1e-9)
    assert row["se"] == pytest.approx(se, abs=1e-9)
    assert row["ci_low"] == pytest.approx(lift - z * se, abs=1e-9)
    assert row["ci_high"] == pytest.approx(lift + z * se, abs=1e-9)
    assert row["p1_avg"] == pytest.approx((w_low * p1_low + w_high * p1_high) / sum_w, abs=1e-9)
    assert row["p0_avg"] == pytest.approx((w_low * p0_low + w_high * p0_high) / sum_w, abs=1e-9)
    assert (row["n_did"], row["n_did_not"]) == (9, 11)
    assert row["action"] == "act_x"


def test_cells_are_separate(cfg):
    one = hand_points()
    two = pd.concat([one.assign(module="A"), one.assign(module="B", course_id="D")])
    pooled = estimate_lifts(one, [], "effort", ["act_x"], "goal", cfg).iloc[0]
    per_cell = estimate_lifts(two, ["module"], "effort", ["act_x"], "goal", cfg)
    assert list(per_cell["module"]) == ["A", "B"]
    assert np.allclose(per_cell["lift"], pooled["lift"], atol=1e-12)


def lift_row(cells: dict, action: str, lift: float, ci_low: float, n: int) -> dict:
    return {**cells, "action": action, "lift": lift, "se": 0.01, "ci_low": ci_low,
            "ci_high": lift + 0.02, "p1_avg": 0.6, "p0_avg": 0.5, "n_did": n,
            "n_did_not": n, "base_rate": 0.5}


def state(module, block, score, effort):
    return {"module": module, "week_block": block, "score_band": score, "effort_band": effort}


def test_support_back_off_and_statuses(cfg):
    level0 = pd.DataFrame([
        # Winner: y has a higher lift but ci_low <= 0. z is not supported.
        lift_row(state("A", "early", "high", "high"), "x", 0.05, 0.01, 40),
        lift_row(state("A", "early", "high", "high"), "y", 0.09, -0.01, 40),
        lift_row(state("A", "early", "high", "high"), "z", 0.50, 0.40, 29),
        # Supported, no positive ci_low: no_clear_winner, no back-off.
        lift_row(state("A", "early", "mid", "mid"), "x", 0.02, -0.01, 40),
        # Not supported: back off to level 1.
        lift_row(state("A", "early", "low", "low"), "x", 0.30, 0.20, 10),
    ])
    level1 = pd.DataFrame([
        lift_row({k: v for k, v in state("A", "", "mid", "mid").items() if k != "week_block"},
                 "w", 0.10, 0.05, 100),
        lift_row({"module": "A", "score_band": "low", "effort_band": "low"}, "w", 0.07, 0.03, 30),
    ])
    level2 = pd.DataFrame([
        lift_row({"score_band": "none", "effort_band": "none"}, "v", 0.04, 0.02, 500),
    ])
    best = best_actions({0: level0, 1: level1, 2: level2}, cfg)
    points = pd.DataFrame([
        state("A", "early", "high", "high"),
        state("A", "early", "mid", "mid"),
        state("A", "early", "low", "low"),
        state("B", "late", "none", "none"),
        state("B", "late", "high", "low"),
    ])
    out = resolve_points(points, best)
    assert list(out["status"]) == [RECOMMEND, NO_CLEAR_WINNER, RECOMMEND, RECOMMEND, ABSTAIN]
    assert list(out["action"]) == ["x", None, "w", "v", None]
    assert list(out["level"].astype(object)) == [0, 0, 1, 2, pd.NA]
    assert out.loc[2, "n_did"] == 30
    assert np.isnan(out.loc[1, "lift"])

    strict = best_actions({0: level0, 1: level1, 2: level2}, replace(cfg, min_count=41))
    out = resolve_points(points.iloc[[0]], strict)
    assert out.loc[0, "status"] == ABSTAIN


def test_levels_match_spec():
    assert LEVELS == {
        0: ["module", "week_block", "score_band", "effort_band"],
        1: ["module", "score_band", "effort_band"],
        2: ["score_band", "effort_band"],
    }
