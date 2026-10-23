"""make eval: baselines, evaluation, fairness, reports and figures (SPEC sections 14 to 17)."""

import json

import numpy as np
import pandas as pd

from liftpath.adapters.synthetic import TRUE_EFFECT_ACTIONS
from liftpath.baselines import (
    make_course_order,
    make_liftpath,
    make_popular,
    make_random,
    make_raw_success,
    make_user_cf,
)
from liftpath.config import Config
from liftpath.evaluate import evaluate_all
from liftpath.fairness import ATTRIBUTES, subgroup_report
from liftpath.figures import eval_lift_figure, fairness_figure, synthetic_truth_figure
from liftpath.lift import (
    ABSTAIN,
    NO_CLEAR_WINNER,
    RECOMMEND,
    STUDENT_KEY,
    best_actions,
    estimate_lifts,
    lift_tables,
    resolve_points,
)
from liftpath.paths import REPORTS_DIR, canonical_dir, scope_dir

GOALS = {"goal_pass": "pass", "goal_distinction": "distinction"}
PRIMARY = "goal_pass"
ORDER = ["random", "popular", "course_order", "user_cf", "raw_success", "liftpath"]


def pp(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value * 100:+.1f} pp"


def span(low: float, high: float) -> str:
    return "n/a" if pd.isna(low) else f"{pp(low)} to {pp(high)}"


def cached(actions: pd.Series):
    return lambda points: actions.loc[points.index]


def results_table(results: pd.DataFrame) -> str:
    lines = ["| recommender | coverage | follower lift | 95% range | net lift | 95% range |",
             "|---|---|---|---|---|---|"]
    for r in results.itertuples():
        lines.append(f"| {r.name} | {r.coverage:.1%} | {pp(r.lift)} | {span(r.ci_low, r.ci_high)}"
                     f" | {pp(r.net_lift)} | {span(r.net_ci_low, r.net_ci_high)} |")
    return "\n".join(lines)


def common_table(results: pd.DataFrame) -> str:
    lines = ["| recommender | follower lift | 95% range | net lift | 95% range |",
             "|---|---|---|---|---|"]
    for r in results.itertuples():
        lines.append(f"| {r.name} | {pp(r.common_lift)} | "
                     f"{span(r.common_ci_low, r.common_ci_high)} | {pp(r.common_net_lift)} | "
                     f"{span(r.common_net_ci_low, r.common_net_ci_high)} |")
    return "\n".join(lines)


def reference_table(results: pd.DataFrame) -> str:
    lines = ["| recommender | all test points | 95% range | common subset | 95% range |",
             "|---|---|---|---|---|"]
    for r in results[results["name"] != "liftpath"].itertuples():
        lines.append(f"| {r.name} | {pp(r.ref_minus)} | "
                     f"{span(r.ref_minus_ci_low, r.ref_minus_ci_high)} | "
                     f"{pp(r.common_ref_minus)} | "
                     f"{span(r.common_ref_minus_ci_low, r.common_ref_minus_ci_high)} |")
    return "\n".join(lines)


def truth_table(actions: dict[str, pd.Series]) -> tuple[pd.DataFrame, str]:
    """Synthetic only: per recommender, the share of its actions that have a true effect."""
    shares = pd.DataFrame({name: a.value_counts(normalize=True) for name, a in actions.items()})
    lines = ["| recommender | recommendations | share with a true effect (quiz) | "
             "share forumng |", "|---|---|---|---|"]
    for name, a in actions.items():
        given = a.dropna()
        true_share = given.isin(TRUE_EFFECT_ACTIONS).mean() if len(given) else np.nan
        lines.append(f"| {name} | {len(given):,} | {true_share:.1%} | "
                     f"{(given == 'forumng').mean():.1%} |")
    return shares.fillna(0), "\n".join(lines)


def suffix(cfg: Config) -> str:
    return "" if cfg.scope == "full" else f"_{cfg.scope}"


def run_eval(cfg: Config) -> dict:
    folder = scope_dir(cfg)
    points = pd.read_parquet(folder / "decision_points.parquet")
    candidates = json.loads((folder / "candidates.json").read_text(encoding="utf-8"))
    train = points[points["split"] == "train"]
    test = points[points["split"] == "test"].reset_index(drop=True)
    figures = REPORTS_DIR / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    shared = {
        "random": make_random(candidates, cfg.seed)(test),
        "popular": make_popular(train, candidates, cfg)(test),
        "course_order": make_course_order(train, candidates)(test),
        "user_cf": make_user_cf(train, candidates, cfg)(test),
    }
    output = {"scope": cfg.scope, "n_train_points": len(train), "n_test_points": len(test),
              "n_test_students": int(test[STUDENT_KEY].drop_duplicates().shape[0]),
              "candidates": candidates, "goals": {}}
    md = [f"# Evaluation ({cfg.scope} scope)", "",
          f"Train points: {len(train):,}. Test points: {len(test):,} "
          f"({output['n_test_students']:,} students). Candidates: {', '.join(candidates)}.", "",
          "Follower lift compares test students who did the recommended activity next week with "
          "students who did not, in the same level 0 cell and next-week effort band. The 95% "
          f"range comes from a bootstrap that resamples students ({cfg.n_boot} runs). "
          "Coverage is the share of test points that get an action.", "",
          "The random recommender also shows a positive follower lift, because engaged students "
          "do more of everything and pass more. This is the bias floor. Net lift subtracts it, "
          "with a paired bootstrap range. Net lift is the honest result.", "",
          "Follower lift uses the same next-week effort bands as LiftPath. If an activity is "
          "driven by effort, both can rate it too high. The ground truth check on synthetic data "
          "(`eval_synthetic.md`) tests this against a known answer.", ""]

    for goal, goal_name in GOALS.items():
        tables = lift_tables(train, candidates, goal, cfg)
        actions = {**shared,
                   "raw_success": make_raw_success(train, candidates, goal, cfg)(test),
                   "liftpath": make_liftpath(tables, goal, cfg)(test)}
        actions = {name: actions[name] for name in ORDER}
        results = evaluate_all(test, {n: cached(a) for n, a in actions.items()}, goal, cfg,
                               reference="liftpath")
        status = resolve_points(test, best_actions(tables, cfg))["status"]
        shares = {s: float((status == s).mean()) for s in (RECOMMEND, NO_CLEAR_WINNER, ABSTAIN)}
        common_n = int(results["common_n_points"].iloc[0])
        output["goals"][goal] = {"results": results.to_dict("records"),
                                 "liftpath_status_shares": shares, "common_n_points": common_n}
        md += [f"## Goal: {goal_name}", "", results_table(results), "",
               f"LiftPath status shares: recommend {shares[RECOMMEND]:.1%}, no_clear_winner "
               f"{shares[NO_CLEAR_WINNER]:.1%}, abstain {shares[ABSTAIN]:.1%}. LiftPath gives an "
               "action only for recommend, so its coverage above is the recommend share.", "",
               f"### Common subset ({common_n:,} test points where every recommender gives an "
               "action)", "", common_table(results), "",
               "### LiftPath minus each recommender (paired bootstrap)", "",
               "A range above zero means LiftPath has the higher follower lift.", "",
               reference_table(results), ""]

        if goal == PRIMARY:
            eval_lift_figure(results, goal_name, figures / f"eval_lift{suffix(cfg)}.png")
            gate3 = 1 - shares[ABSTAIN]
            output["gate3"] = {"coverage_not_abstain": gate3, "min": cfg.gate_coverage_min,
                               "passes": bool(gate3 >= cfg.gate_coverage_min)}
            write_fairness(cfg, test, status, actions["liftpath"], goal, results, figures)
            if cfg.scope == "synthetic":
                md += synthetic_section(cfg, train, candidates, actions, figures)

    g3 = output["gate3"]
    md += ["## Gate 3", "",
           f"LiftPath coverage (status is not abstain) for the pass goal: "
           f"{g3['coverage_not_abstain']:.1%}. The gate needs {cfg.gate_coverage_min:.0%}. "
           f"Result: {'PASS' if g3['passes'] else 'FAIL'}"
           f"{'' if cfg.scope == 'full' else ' (the gate counts only on full data)'}.", "",
           "## Figures", "", f"- `figures/eval_lift{suffix(cfg)}.png`",
           f"- `figures/fairness{suffix(cfg)}.png`"]
    if cfg.scope == "synthetic":
        md.append("- `figures/synthetic_truth.png`")
    (REPORTS_DIR / f"eval{suffix(cfg)}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (REPORTS_DIR / f"eval_results{suffix(cfg)}.json").write_text(
        json.dumps(output, indent=2, default=float), encoding="utf-8")
    return output


def synthetic_section(cfg: Config, train: pd.DataFrame, candidates: list[str],
                      actions: dict[str, pd.Series], figures) -> list[str]:
    shares, table = truth_table(actions)
    raw = pd.Series({a: train.loc[train[f"act_{a}"], "goal_pass"].mean() for a in candidates})
    pooled = estimate_lifts(train, [], "next_effort_band", [f"act_{a}" for a in candidates],
                            "goal_pass", cfg)
    pooled = pooled.assign(action=pooled["action"].str.removeprefix("act_")).set_index("action")
    synthetic_truth_figure(raw, pooled, shares, TRUE_EFFECT_ACTIONS,
                           figures / "synthetic_truth.png")
    return ["## Ground truth (synthetic data)", "",
            "In the synthetic data, only quiz has a true effect on passing. forumng use rises "
            "with effort, but it has no effect. This table does not depend on follower lift.", "",
            table, "",
            "In the generator, quiz is also a common activity: students use it in about 40% of "
            "their active weeks, at every effort level. The popular and course_order baselines "
            "pick quiz because many students use it, not because they measure its effect.", ""]


def write_fairness(cfg: Config, test: pd.DataFrame, status: pd.Series, actions: pd.Series,
                   goal: str, results: pd.DataFrame, figures) -> None:
    enr = pd.read_parquet(canonical_dir(cfg) / "enrollments.parquet",
                          columns=[*STUDENT_KEY, *ATTRIBUTES])
    with_groups = test.merge(enr, on=STUDENT_KEY, how="left").assign(status=status.to_numpy())
    report = subgroup_report(with_groups, actions, goal, cfg)
    (REPORTS_DIR / f"fairness_results{suffix(cfg)}.json").write_text(
        report.to_json(orient="records", indent=2), encoding="utf-8")
    overall = float(results.set_index("name").loc["liftpath", "lift"])
    fairness_figure(report, overall, figures / f"fairness{suffix(cfg)}.png")
    lines = [f"# Fairness ({cfg.scope} scope, goal: pass)", "",
             "LiftPath results per group on test data. Coverage is the share of points where "
             "the status is not abstain. Recommend share is the share that gets an action. "
             "Follower lift has a 95% range from a student bootstrap. A group with fewer than "
             "200 unique students is a small sample.", "",
             "| attribute | group | students | points | coverage | recommend share | "
             "follower lift | 95% range | note |", "|---|---|---|---|---|---|---|---|---|"]
    for r in report.itertuples():
        lines.append(f"| {r.attribute} | {r.group} | {r.n_students:,} | {r.n_points:,} | "
                     f"{r.coverage:.1%} | {r.recommend_share:.1%} | {pp(r.lift)} | "
                     f"{span(r.ci_low, r.ci_high)} | "
                     f"{'small sample' if r.small_sample else ''} |")
    lines += ["", f"All test points: follower lift {pp(overall)}."]
    (REPORTS_DIR / f"fairness{suffix(cfg)}.md").write_text("\n".join(lines) + "\n",
                                                          encoding="utf-8")
