from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.lift import ABSTAIN, NO_CLEAR_WINNER, RECOMMEND
from liftpath.recommend import State, label, recommend, recommend_points

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    return load_config(CONFIG_PATH)


def row(cells, action="quiz", lift=0.07, ci_low=0.02, n_did=40, n_did_not=50):
    return {**cells, "action": action, "lift": lift, "se": 0.025, "ci_low": ci_low,
            "ci_high": 0.12, "p1_avg": 0.62, "p0_avg": 0.55, "n_did": n_did,
            "n_did_not": n_did_not, "base_rate": 0.58}


def cells(level, module, block, score, effort):
    full = {"module": module, "week_block": block, "score_band": score, "effort_band": effort}
    keep = {0: full, 1: {k: v for k, v in full.items() if k != "week_block"},
            2: {"score_band": score, "effort_band": effort}}
    return keep[level]


def tables():
    return {
        0: pd.DataFrame([
            row(cells(0, "AAA", "early", "high", "mid")),
            row(cells(0, "AAA", "late", "mid", "mid"), ci_low=-0.01),
        ]),
        1: pd.DataFrame([row(cells(1, "BBB", "", "low", "high"), action="forumng")]),
        2: pd.DataFrame([row(cells(2, "", "", "none", "none"), action="oucontent")]),
    }


TAIL = (" who studied about as much as you did next week: those who used {label} reached a "
        "pass 62% of the time. Those who did not reached it 55% of the time. Lift: +7% "
        "(95% range +2% to +12%). Based on 40 and 50 students.")


def test_recommend_level_0(cfg):
    rec = recommend(State("AAA", "early", "high", "mid"), "goal_pass", tables(), cfg)
    assert rec.status == RECOMMEND
    assert rec.estimate.level == 0 and rec.estimate.action == "quiz"
    assert rec.rationale == ("Students in a similar situation (AAA, early weeks, high scores, "
                             "mid effort)" + TAIL.format(label="quizzes"))


def test_recommend_level_1_drops_weeks(cfg):
    rec = recommend(State("BBB", "mid", "low", "high"), "goal_pass", tables(), cfg)
    assert rec.estimate.level == 1
    assert rec.rationale == ("Students in a similar situation (BBB, low scores, high effort) "
                             "(compared across all weeks)"
                             + TAIL.format(label="discussion forum"))


def test_recommend_level_2_drops_courses(cfg):
    rec = recommend(State("CCC", "late", "none", "none"), "goal_pass", tables(), cfg)
    assert rec.estimate.level == 2
    assert rec.rationale == ("Students in a similar situation (no scores yet, no activity this "
                             "week) (compared across all courses)"
                             + TAIL.format(label="course pages"))


def test_no_clear_winner_and_abstain(cfg):
    rec = recommend(State("AAA", "late", "mid", "mid"), "goal_pass", tables(), cfg)
    assert (rec.status, rec.estimate) == (NO_CLEAR_WINNER, None)
    assert rec.rationale == "No clear winner. Continue your current plan."
    rec = recommend(State("ZZZ", "late", "high", "low"), "goal_pass", tables(), cfg)
    assert (rec.status, rec.estimate) == (ABSTAIN, None)
    assert rec.rationale == "Not enough similar students to compare."


def test_small_counts_are_hidden_in_text(cfg):
    small = {0: pd.DataFrame([row(cells(0, "AAA", "early", "high", "mid"), n_did=3)])}
    rec = recommend(State("AAA", "early", "high", "mid"), "goal_distinction", small,
                    replace(cfg, min_count=1))
    assert "Based on fewer than 5 and 50 students." in rec.rationale
    assert "reached a distinction" in rec.rationale


def test_recommend_points_matches_single(cfg):
    states = [State("AAA", "early", "high", "mid"), State("AAA", "late", "mid", "mid"),
              State("ZZZ", "late", "high", "low")]
    points = pd.DataFrame([s.__dict__ for s in states])
    out = recommend_points(points, "goal_pass", tables(), cfg)
    assert list(out["status"]) == [recommend(s, "goal_pass", tables(), cfg).status
                                   for s in states]


def test_labels():
    assert label("ouelluminate") == "live sessions"
    assert label("newtype") == "newtype"
