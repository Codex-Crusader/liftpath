"""Simulator (BUILD2 Phase B) at dev sizes: Wald estimator, explore share, common random
numbers and one small run of all policies."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from liftpath.adapters.synthetic import SyntheticParams
from liftpath.config import load_config
from liftpath.sim import (
    POLICIES,
    build_policy,
    run_world,
    sim_candidates,
    simulate_cohort,
    wald_effects,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
STATE_COLS = ["course_id", "student_id", "week", "week_block", "score_band", "effort_band",
              "clicks_week"]


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def candidates(cfg):
    return sim_candidates(SyntheticParams(), cfg)


def wald_fixture(n_per_arm: int) -> pd.DataFrame:
    """One explored decision per student. rec = quiz: 60% use quiz, 50% pass.
    rec = forumng: 10% use quiz, 30% pass. Forum use is 50% in both arms."""
    def arm(rec: str, quiz_share: float, pass_share: float, first_id: int) -> pd.DataFrame:
        i = np.arange(n_per_arm)
        return pd.DataFrame({
            "course_id": "C", "student_id": first_id + i, "rec_action": rec,
            "act_quiz": i < quiz_share * n_per_arm, "act_forumng": i % 2 == 0,
            "goal_pass": i < pass_share * n_per_arm})
    return pd.concat([arm("quiz", 0.6, 0.5, 0), arm("forumng", 0.1, 0.3, n_per_arm)],
                     ignore_index=True)


def test_wald_known_answer(cfg):
    out = wald_effects(wald_fixture(100), ["quiz", "forumng"], cfg,
                       np.random.default_rng(cfg.seed)).set_index("action")
    quiz = out.loc["quiz"]
    assert quiz["itt"] == pytest.approx(0.2)
    assert quiz["first_stage"] == pytest.approx(0.5)
    assert quiz["effect"] == pytest.approx(0.4)
    assert quiz["available"]
    assert quiz["ci_low"] < 0.4 < quiz["ci_high"]
    # Forum use does not change with the recommendation: no first stage.
    assert out.loc["forumng", "first_stage"] == pytest.approx(0.0)
    assert not out.loc["forumng", "available"]


def test_wald_needs_min_count(cfg):
    small = wald_fixture(cfg.min_count // 2)
    out = wald_effects(small, ["quiz"], cfg, np.random.default_rng(cfg.seed))
    assert not out["available"].iloc[0]


def test_explored_share(cfg, candidates):
    n = cfg.sim_dev_students
    history = simulate_cohort("standard", 0, n, None, candidates, cfg)
    rng = np.random.default_rng(cfg.seed)
    policy, _ = build_policy("liftpath_explore", history.points, candidates, cfg, rng)
    run = simulate_cohort("standard", 1, n, policy, candidates, cfg)
    assert abs(run.points["explored"].mean() - cfg.sim_explore_share) <= 0.05


def test_common_random_numbers(cfg, candidates):
    n = cfg.sim_dev_students
    first = simulate_cohort("hidden_confounder", 0, n, None, candidates, cfg)
    second = simulate_cohort("hidden_confounder", 0, n, None, candidates, cfg)
    pd.testing.assert_frame_equal(first.points, second.points)
    pd.testing.assert_frame_equal(first.students, second.students)

    # Cohort 1 under two policies: week 0 comes before any advice, so it is the same.
    history = first.points
    runs = []
    for name in ("none", "random"):
        policy, _ = build_policy(name, history, candidates, cfg, np.random.default_rng(1))
        runs.append(simulate_cohort("hidden_confounder", 1, n, policy, candidates, cfg))
    week0 = [r.points.loc[r.points["week"] == 0, STATE_COLS].reset_index(drop=True)
             for r in runs]
    pd.testing.assert_frame_equal(week0[0], week0[1])
    assert runs[1].points["rec_action"].notna().all()


def test_run_world_dev(cfg):
    results, estimates = run_world("hidden_confounder", cfg, cfg.sim_dev_students,
                                   cfg.sim_dev_cohorts)
    assert len(results) == len(POLICIES) * cfg.sim_dev_cohorts
    assert results["pass_rate"].between(0, 1).all()
    advised = results[(results["cohort"] > 0) & (results["policy"] != "none")]
    assert (advised["rec_rate"] > 0).all()
    assert set(estimates["kind"]) == {"observational"}
