"""Headline numbers for the app header, the README and the slides (BUILD2 Phase G)."""

import pandas as pd

from liftpath.config import Config

GOAL = "goal_pass"
FINDING = "finding"
MEASUREMENT = "measurement"
FIRST_MEAN_COHORT = 2
WORLD_NAMES = {"standard": "standard world", "hidden_confounder": "hidden confounder world"}


def pp(value: float) -> str:
    return f"{100 * value:+.1f} pp"


def real_numbers(goal_data: dict) -> dict:
    """The eval values that the story rule and the text use, for one goal."""
    rows = pd.DataFrame(goal_data["results"]).set_index("name")
    lp, cf, raw = rows.loc["liftpath"], rows.loc["user_cf"], rows.loc["raw_success"]
    return {
        "disagree_user_cf": goal_data["disagreement"]["user_cf"],
        "disagree_raw_success": goal_data["disagreement"]["raw_success"],
        "common_n_points": goal_data["common_n_points"],
        "liftpath_net": lp["net_lift"], "liftpath_net_ci_low": lp["net_ci_low"],
        "liftpath_net_ci_high": lp["net_ci_high"], "liftpath_coverage": lp["coverage"],
        "user_cf_net": cf["net_lift"], "user_cf_net_ci_low": cf["net_ci_low"],
        "user_cf_net_ci_high": cf["net_ci_high"], "user_cf_coverage": cf["coverage"],
        "raw_success_net": raw["net_lift"],
        "common_liftpath_net": lp["common_net_lift"], "common_user_cf_net": cf["common_net_lift"],
        "minus_raw_success_common": raw["common_ref_minus"],
        "minus_raw_success_common_ci_low": raw["common_ref_minus_ci_low"],
        "minus_raw_success_common_ci_high": raw["common_ref_minus_ci_high"],
    }


def choose_story(real: dict, cfg: Config) -> tuple[str, str]:
    """BUILD2 Phase G story rule. Returns the story name and the headline sentence."""
    finding = (real["disagree_user_cf"] >= cfg.trap_disagree_min
               and real["liftpath_net_ci_low"] > 0
               and real["user_cf_net"] <= real["liftpath_net"])
    if finding:
        return FINDING, (
            f"Common advice and helpful advice differ for {real['disagree_user_cf']:.0%} of "
            f"decisions. LiftPath advice: {100 * real['liftpath_net']:+.1f} points net lift. "
            f"Collaborative filtering: {100 * real['user_cf_net']:+.1f}.")
    return MEASUREMENT, "We measured which advice helps."


def sim_numbers(results: pd.DataFrame) -> dict:
    """Pass rate gains per world: the final cohort and the mean over cohorts 2 to last."""
    last = int(results["cohort"].max())
    advised = results[results["cohort"].between(FIRST_MEAN_COHORT, last)]
    final = results[results["cohort"] == last].pivot(index="policy", columns="world",
                                                       values="pass_rate")
    mean = advised.groupby(["policy", "world"])["pass_rate"].mean().unstack("world")
    out = {"last_cohort": last, "first_mean_cohort": FIRST_MEAN_COHORT, "worlds": {}}
    for world in final.columns:
        f, m = final[world], mean[world]
        out["worlds"][world] = {
            "final": f.to_dict(), "mean": m.to_dict(),
            "liftpath_minus_none": {"final": f["liftpath"] - f["none"],
                                    "mean": m["liftpath"] - m["none"]},
            "liftpath_minus_user_cf": {"final": f["liftpath"] - f["user_cf"],
                                       "mean": m["liftpath"] - m["user_cf"]},
            "explore_minus_none": {"final": f["liftpath_explore"] - f["none"],
                                   "mean": m["liftpath_explore"] - m["none"]},
            "explore_minus_liftpath": {"final": f["liftpath_explore"] - f["liftpath"],
                                       "mean": m["liftpath_explore"] - m["liftpath"]},
            "best_mean_policy": m.idxmax(),
        }
    return out


def metrics(real: dict, sim: dict) -> list[dict]:
    """The app header items (format in PROGRESS.md, Phase F)."""
    std = sim["worlds"]["standard"]["liftpath_minus_none"]
    return [
        {"label": "Differs from 'similar students' advice",
         "value": f"{real['disagree_user_cf']:.0%}",
         "help": f"Share of {real['common_n_points']:,} common test student-weeks where "
                 "LiftPath and collaborative filtering give different activities."},
        {"label": "LiftPath net lift (pass)", "value": pp(real["liftpath_net"]),
         "help": f"95% range {pp(real['liftpath_net_ci_low'])} to "
                 f"{pp(real['liftpath_net_ci_high'])}. Test students. LiftPath advises on "
                 f"{real['liftpath_coverage']:.0%} of student-weeks."},
        {"label": "Collaborative filtering net lift", "value": pp(real["user_cf_net"]),
         "help": f"95% range {pp(real['user_cf_net_ci_low'])} to "
                 f"{pp(real['user_cf_net_ci_high'])}. Test students."},
        {"label": "Simulator: LiftPath minus no advice", "value": pp(std["final"]),
         "help": f"Standard world, pass rate in cohort {sim['last_cohort']}. Mean over cohorts "
                 f"{sim['first_mean_cohort']} to {sim['last_cohort']}: {pp(std['mean'])}. "
                 "Synthetic students."},
    ]


def build_headline(eval_results: dict, results: pd.DataFrame, cfg: Config) -> dict:
    real = real_numbers(eval_results["goals"][GOAL])
    story, sentence = choose_story(real, cfg)
    sim = sim_numbers(results)
    return {"story": story, "headline": sentence, "goal": GOAL,
            "trap_disagree_min": cfg.trap_disagree_min, "real": real, "sim": sim,
            "metrics": metrics(real, sim)}


def sim_lines(sim: dict) -> list[str]:
    last, first = sim["last_cohort"], sim["first_mean_cohort"]
    lines = []
    for world in WORLD_NAMES:
        data = sim["worlds"][world]
        none, cf = data["liftpath_minus_none"], data["liftpath_minus_user_cf"]
        lines.append(
            f"- {WORLD_NAMES[world].capitalize()}: LiftPath minus no advice "
            f"{pp(none['final'])} in cohort {last} ({pp(none['mean'])} as the mean of cohorts "
            f"{first} to {last}). LiftPath minus collaborative filtering {pp(cf['final'])} "
            f"({pp(cf['mean'])} mean). The best mean pass rate: {data['best_mean_policy']}.")
    hidden = sim["worlds"]["hidden_confounder"]
    ex_none, ex_lp = hidden["explore_minus_none"], hidden["explore_minus_liftpath"]
    lines.append(
        f"- Hidden confounder world, LiftPath + explore: minus no advice {pp(ex_none['final'])} "
        f"in cohort {last} ({pp(ex_none['mean'])} mean), minus greedy LiftPath "
        f"{pp(ex_lp['final'])} ({pp(ex_lp['mean'])} mean).")
    return lines


def headline_markdown(h: dict) -> str:
    r = h["real"]
    story = ("Finding" if h["story"] == FINDING else "Measurement")
    text = [
        "# LiftPath headline",
        "",
        f"Story: {story} (rule in BUILD2 Phase G, threshold {h['trap_disagree_min']:.0%}).",
        "",
        h["headline"],
        "",
        "## Real data (OULAD test students, goal: pass)",
        "",
        f"- LiftPath and collaborative filtering (user_cf) give different activities for "
        f"{r['disagree_user_cf']:.1%} of {r['common_n_points']:,} common test student-weeks. "
        f"LiftPath and raw_success differ for {r['disagree_raw_success']:.1%}.",
        f"- Net lift (follower lift minus the random advice lift): LiftPath "
        f"{pp(r['liftpath_net'])} (95% range {pp(r['liftpath_net_ci_low'])} to "
        f"{pp(r['liftpath_net_ci_high'])}), user_cf {pp(r['user_cf_net'])} (95% range "
        f"{pp(r['user_cf_net_ci_low'])} to {pp(r['user_cf_net_ci_high'])}), raw_success "
        f"{pp(r['raw_success_net'])}.",
        f"- LiftPath gives an activity for {r['liftpath_coverage']:.1%} of test student-weeks. "
        f"user_cf gives one for {r['user_cf_coverage']:.1%}. On the common subset, where all "
        f"methods give an activity, the net lifts are {pp(r['common_liftpath_net'])} "
        f"(LiftPath) and {pp(r['common_user_cf_net'])} (user_cf).",
        f"- LiftPath minus raw_success on the common subset: "
        f"{pp(r['minus_raw_success_common'])} (95% range "
        f"{pp(r['minus_raw_success_common_ci_low'])} to "
        f"{pp(r['minus_raw_success_common_ci_high'])}). For the pass goal, LiftPath does not "
        "beat raw_success there.",
        "",
        "## Simulator (synthetic students with a known truth)",
        "",
        *sim_lines(h["sim"]),
        "- popular has the best mean pass rate in both worlds. In this world the most used "
        "activity (quiz) is also the only one with a true effect, so popularity and help "
        "point the same way. On real data, popular has a lower net lift than LiftPath.",
        "- The final cohort alone can mislead, because LiftPath + explore swings from cohort "
        "to cohort. Compare the means.",
        "- The explore gain in the hidden confounder world depends on an upward bias of the "
        "explore estimate. The quiz range is above 0 only in the cohorts where the estimate is "
        "about 2 to 2.5 times the true effect. With a larger explore share (0.4), the "
        "estimates are near the truth, and LiftPath + explore does not move to quiz.",
        "",
        "The data is observational. Lift is evidence, not proof of cause.",
        "",
    ]
    return "\n".join(text)
