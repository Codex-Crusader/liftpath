"""Story rule and simulator numbers of the headline (BUILD2 Phase G)."""

from pathlib import Path

import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.headline import FINDING, MEASUREMENT, build_headline, choose_story, sim_numbers

ROOT = Path(__file__).resolve().parent.parent
CFG = load_config(ROOT / "config.yaml")
POLICIES = ("none", "user_cf", "liftpath", "liftpath_explore", "popular")


def real(disagree=0.5, lp=0.03, lp_low=0.02, cf=0.01) -> dict:
    return {"disagree_user_cf": disagree, "liftpath_net": lp, "liftpath_net_ci_low": lp_low,
            "user_cf_net": cf}


def test_finding_needs_all_three_conditions():
    story, text = choose_story(real(), CFG)
    assert story == FINDING
    assert text == ("Common advice and helpful advice differ for 50% of decisions. LiftPath "
                    "advice: +3.0 points net lift. Collaborative filtering: +1.0.")
    for case in (real(disagree=CFG.trap_disagree_min - 0.01), real(lp_low=0.0),
                 real(cf=0.04)):
        assert choose_story(case, CFG) == (MEASUREMENT, "We measured which advice helps.")
    assert choose_story(real(disagree=CFG.trap_disagree_min, cf=0.03), CFG)[0] == FINDING


def sim_results() -> pd.DataFrame:
    rows = []
    for world in ("standard", "hidden_confounder"):
        for i, policy in enumerate(POLICIES):
            for cohort in range(4):
                rows.append({"world": world, "policy": policy, "cohort": cohort,
                             "pass_rate": 0.4 + 0.01 * i * cohort})
    return pd.DataFrame(rows)


def test_sim_numbers_final_and_mean():
    sim = sim_numbers(sim_results())
    assert sim["last_cohort"] == 3
    std = sim["worlds"]["standard"]
    # liftpath is policy 2, none is policy 0: final gain 0.02 * 3, mean over cohorts 2 and 3.
    assert std["liftpath_minus_none"]["final"] == pytest.approx(0.06)
    assert std["liftpath_minus_none"]["mean"] == pytest.approx(0.05)
    assert std["explore_minus_liftpath"]["final"] == pytest.approx(0.03)
    assert std["best_mean_policy"] == "popular"


def test_headline_metrics_format():
    goal = {"results": [{"name": n, "net_lift": v, "net_ci_low": v - 0.01,
                         "net_ci_high": v + 0.01, "coverage": 0.9, "common_net_lift": v,
                         "common_ref_minus": 0.0, "common_ref_minus_ci_low": -0.01,
                         "common_ref_minus_ci_high": 0.01}
                        for n, v in (("liftpath", 0.03), ("user_cf", 0.0),
                                     ("raw_success", 0.02))],
            "disagreement": {"user_cf": 0.7, "raw_success": 0.5}, "common_n_points": 100}
    out = build_headline({"goals": {"goal_pass": goal}}, sim_results(), CFG)
    assert out["story"] == FINDING
    assert 2 <= len(out["metrics"]) <= 4
    for item in out["metrics"]:
        assert set(item) == {"label", "value", "help"}
        assert isinstance(item["value"], str)
