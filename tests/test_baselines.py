from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from liftpath.baselines import (
    make_course_order,
    make_popular,
    make_random,
    make_raw_success,
    make_user_cf,
)
from liftpath.config import load_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CANDIDATES = ["x", "y"]


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    return replace(load_config(CONFIG_PATH), min_count=2, cf_neighbors=2)


def point(module, block, act_x, act_y, goal, share_x=0.5, week=1):
    return {"module": module, "week_block": block, "score_band": "mid", "effort_band": "mid",
            "week": week, "act_x": act_x, "act_y": act_y, "goal": goal,
            "cum_share_x": share_x, "cum_share_y": 1 - share_x}


def train_points():
    return pd.DataFrame([
        point("A", "early", True, False, False),
        point("A", "early", True, False, False),
        point("A", "early", False, True, True),
        point("A", "late", False, True, True),
        point("A", "late", False, True, True),
        point("A", "late", True, False, False),
    ])


def test_popular_backs_off(cfg):
    test = pd.DataFrame([point("A", "early", False, False, False),
                         point("A", "mid", False, False, False),
                         point("B", "mid", False, False, False)])
    actions = make_popular(train_points(), CANDIDATES, cfg)(test)
    # A early: x used most. A mid: unseen, back off to A (3 x, 3 y: tie goes to x).
    assert list(actions) == ["x", "x", "x"]


def test_raw_success_needs_min_count(cfg):
    test = pd.DataFrame([point("A", "early", False, False, False),
                         point("A", "late", False, False, False),
                         point("A", "mid", False, False, False)])
    # A early: only x has n1 >= 2, so x wins with a success rate of 0.
    # A late: only y has n1 >= 2. A mid: unseen, back off to A, where y has 3 of 3.
    actions = make_raw_success(train_points(), CANDIDATES, "goal", cfg)(test)
    assert list(actions) == ["x", "y", "y"]
    strict = replace(cfg, min_count=10)
    assert make_raw_success(train_points(), CANDIDATES, "goal", strict)(test).iloc[0] is None


def test_course_order_unseen_week_is_none(cfg):
    test = pd.DataFrame([point("A", "early", False, False, False, week=1),
                         point("A", "early", False, False, False, week=9)])
    assert list(make_course_order(train_points(), CANDIDATES)(test)) == ["x", None]


def test_user_cf_uses_nearest_neighbors(cfg):
    train = pd.DataFrame([
        point("A", "early", True, False, False, share_x=1.0),
        point("A", "early", True, False, False, share_x=0.9),
        point("A", "early", False, True, False, share_x=0.0),
        point("A", "early", False, True, False, share_x=0.1),
    ])
    test = pd.DataFrame([point("A", "early", False, False, False, share_x=0.95),
                         point("A", "early", False, False, False, share_x=0.05)])
    assert list(make_user_cf(train, CANDIDATES, cfg)(test)) == ["x", "y"]


def test_random_is_seeded(cfg):
    test = pd.DataFrame([point("A", "early", False, False, False)] * 20)
    rec = make_random(CANDIDATES, 1)
    assert rec(test).tolist() == rec(test).tolist()
    assert set(rec(test)) <= set(CANDIDATES)
