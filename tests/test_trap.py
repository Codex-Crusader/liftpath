"""Trap comparison (BUILD2 Phase C): card text and the disagreement rate."""

import numpy as np
import pandas as pd

from liftpath.recommend import label
from liftpath.trap import disagreement, trap_lines, trap_text


def test_agree():
    text = trap_text("user_cf", "quiz", "quiz", 0.05, 0.01, 0.09)
    assert text == f"Both methods agree: {label('quiz')}."


def test_differ_with_clear_lift():
    text = trap_text("user_cf", "quiz", "forumng", 0.05, 0.01, 0.09)
    assert text.startswith(f"Similar students often do {label('forumng')}.")
    assert "its lift is +5% (range +1% to +9%)." in text
    assert "No clear help." not in text


def test_differ_range_contains_zero():
    text = trap_text("user_cf", "quiz", "forumng", 0.02, -0.02, 0.06)
    assert text.endswith("(range -2% to +6%). No clear help.")


def test_no_advice_and_no_estimate():
    assert trap_text("user_cf", "quiz", None, np.nan, np.nan, np.nan) is None
    assert trap_text("user_cf", "quiz", np.nan, np.nan, np.nan, np.nan) is None
    text = trap_text("raw_success", None, "forumng", np.nan, np.nan, np.nan)
    assert "not enough matched data" in text


def test_trap_lines_skip_missing_method():
    row = pd.Series({"goal_pass_user_cf_action": "forumng", "goal_pass_user_cf_lift": -0.05,
                     "goal_pass_user_cf_ci_low": -0.09, "goal_pass_user_cf_ci_high": -0.01,
                     "goal_pass_raw_success_action": None, "goal_pass_raw_success_lift": np.nan,
                     "goal_pass_raw_success_ci_low": np.nan,
                     "goal_pass_raw_success_ci_high": np.nan})
    lines = trap_lines(row, "goal_pass", "quiz")
    assert len(lines) == 1
    assert "its lift is -5%" in lines[0]


def test_disagreement_counts_only_both_actions():
    liftpath = pd.Series(["quiz", "quiz", None, "forumng"])
    other = pd.Series(["quiz", "forumng", "quiz", None])
    assert disagreement(liftpath, other) == 0.5
    assert np.isnan(disagreement(pd.Series([None]), pd.Series(["quiz"])))
