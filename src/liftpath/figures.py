"""Report figures (matplotlib, Agg backend). Colors come from liftpath.style."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from liftpath.style import (  # noqa: E402
    BLUE,
    GRID,
    METHOD_COLORS,
    MUTED,
    ORANGE,
    SURFACE,
    TEXT,
    TEXT_SECONDARY,
)

OURS = "liftpath"
DPI = 150


def style(ax, title: str, xlabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=TEXT, fontsize=11, pad=10)
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY, fontsize=9)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def percent_points(ax) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 5, 10]))
    ax.xaxis.set_major_formatter(
        lambda v, _: f"{round(v * 100, 2):+g} pp" if round(v * 100, 2) else "0")


def dot_whisker(ax, labels, values, lows, highs, colors, hollow=None) -> None:
    y = np.arange(len(labels))[::-1]
    hollow = hollow if hollow is not None else [False] * len(labels)
    ax.axvline(0, color=MUTED, linewidth=1)
    for yi, v, lo, hi, c, h in zip(y, values, lows, highs, colors, hollow, strict=True):
        ax.plot([lo, hi], [yi, yi], color=c, linewidth=2, solid_capstyle="round")
        ax.plot(v, yi, "o", markersize=8, color=c, markerfacecolor=SURFACE if h else c,
                markeredgewidth=2, markeredgecolor=SURFACE if not h else c)
    ax.set_yticks(y, labels)


def eval_lift_figure(results: pd.DataFrame, goal_name: str, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=SURFACE)
    colors = [BLUE if n == OURS else MUTED for n in results["name"]]
    dot_whisker(axes[0], results["name"], results["lift"], results["ci_low"],
                results["ci_high"], colors)
    style(axes[0], f"Follower lift, goal: {goal_name}", "followers minus non-followers")
    dot_whisker(axes[1], results["name"], results["net_lift"], results["net_ci_low"],
                results["net_ci_high"], colors)
    style(axes[1], "Net lift (minus random)", "difference from the random recommender")
    for ax in axes:
        percent_points(ax)
    fig.text(0.01, 0.01, "Dots: estimate. Lines: 95% range (student cluster bootstrap).",
             color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def synthetic_truth_figure(raw_rates: pd.Series, pooled: pd.DataFrame,
                           shares: pd.DataFrame, true_actions: tuple[str, ...],
                           path: Path) -> None:
    """raw_rates: P(pass | used type) per type. pooled: lift, ci_low, ci_high per type.
    shares: share of recommendations per type, one column per recommender."""
    order = list(pooled.sort_values("lift").index)
    labels = [f"{a} (true effect)" if a in true_actions else a for a in order]
    y = np.arange(len(order))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True, facecolor=SURFACE)

    axes[0].barh(y, raw_rates.reindex(order), height=0.6, color=ORANGE)
    style(axes[0], "Raw success: P(pass | used type)", "pass rate of users")
    axes[0].xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    axes[0].set_xlim(0, 1)

    axes[1].axvline(0, color=MUTED, linewidth=1)
    p = pooled.reindex(order)
    axes[1].hlines(y, p["ci_low"], p["ci_high"], color=BLUE, linewidth=2)
    axes[1].plot(p["lift"], y, "o", markersize=8, color=BLUE, markeredgecolor=SURFACE,
                 markeredgewidth=2)
    style(axes[1], "LiftPath lift, pooled (Gate 2 test)", "effort-matched lift")
    percent_points(axes[1])

    height = 0.38
    for offset, (name, color) in zip((height / 2, -height / 2),
                                     (("liftpath", BLUE), ("raw_success", ORANGE)),
                                     strict=True):
        axes[2].barh(y + offset, shares[name].reindex(order).fillna(0), height=height - 0.04,
                     color=color, label=name)
    style(axes[2], "Share of recommendations", "share of test recommendations")
    axes[2].xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    axes[2].legend(frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, loc="lower right")

    axes[0].set_yticks(y, labels)
    for tick in axes[0].get_yticklabels():
        if "true effect" in tick.get_text():
            tick.set_fontweight("bold")
            tick.set_color(TEXT)
    fig.text(0.01, 0.01, "Synthetic data: only quiz has a true effect on passing. forumng "
             "use rises with effort but has no effect.", color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def fairness_figure(report: pd.DataFrame, overall: float, path: Path) -> None:
    labels = [f"{r.attribute}: {r.group}" + (" (small sample)" if r.small_sample else "")
              for r in report.itertuples()]
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(report) + 1.4), facecolor=SURFACE)
    dot_whisker(ax, labels, report["lift"], report["ci_low"], report["ci_high"],
                [BLUE] * len(report), hollow=list(report["small_sample"]))
    ax.axvline(overall, color=MUTED, linewidth=1, linestyle="--")
    style(ax, "LiftPath follower lift by group", "followers minus non-followers")
    percent_points(ax)
    fig.text(0.01, 0.01, "Dashed line: all test points. Hollow dot: fewer than 200 students.",
             color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


POLICY_NAMES = {"none": "no advice", "random": "random", "popular": "popular",
                "user_cf": "user_cf", "raw_success": "raw_success", "liftpath": "LiftPath",
                "liftpath_explore": "LiftPath + explore"}


def sim_pass_rate_figure(results: pd.DataFrame, world_title: str, path: Path) -> None:
    """Pass rate per cohort and policy. Line ends carry direct labels."""
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    last = results["cohort"].max()
    ends = results[results["cohort"] == last].sort_values("pass_rate")
    for policy, rows in results.groupby("policy", sort=False):
        rows = rows.sort_values("cohort")
        color = METHOD_COLORS[policy]
        ours = policy.startswith("liftpath")
        ax.plot(rows["cohort"], rows["pass_rate"], color=color, linewidth=2.5 if ours else 1.6,
                linestyle="--" if policy == "none" else "-", marker="o", markersize=4,
                zorder=3 if ours else 2)
    # Spread the end labels so they do not overlap.
    span = results["pass_rate"].max() - results["pass_rate"].min()
    gap, previous = 0.045 * span, -np.inf
    for row in ends.itertuples():
        y = max(row.pass_rate, previous + gap)
        previous = y
        ax.text(last + 0.12, y, POLICY_NAMES[row.policy], color=TEXT, fontsize=9,
                va="center")
        ax.plot([last, last + 0.1], [row.pass_rate, y], color=METHOD_COLORS[row.policy],
                linewidth=1)
    style(ax, f"Pass rate by cohort, {world_title}", "cohort (cohort 0: no advice for all)")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xticks(sorted(results["cohort"].unique()))
    ax.set_xlim(-0.2, last + 1.4)
    fig.text(0.01, 0.01, "Simulated students. Each policy trains on cohort 0 and its own "
             "earlier cohorts.", color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def sim_estimates_figure(estimates: pd.DataFrame, path: Path) -> None:
    """Observational and experimental estimates per cohort, with the true effect."""
    kinds = {"observational": ("LiftPath lift (observational)", METHOD_COLORS["liftpath"],
                               -0.1),
             "experimental": ("explore effect (experimental)",
                              METHOD_COLORS["liftpath_explore"], 0.1)}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True, facecolor=SURFACE)
    for ax, action in zip(axes, ("quiz", "resource"), strict=True):
        rows = estimates[estimates["action"] == action]
        truth = rows.groupby("cohort")["true_effect"].first()
        ax.plot(truth.index, truth.to_numpy(), color=TEXT, linewidth=1.2, linestyle="--",
                label="true effect")
        ax.axhline(0, color=MUTED, linewidth=1)
        for kind, (name, color, shift) in kinds.items():
            k = rows[rows["kind"] == kind].sort_values("cohort")
            x = k["cohort"] + shift
            ax.vlines(x, k["ci_low"], k["ci_high"], color=color, linewidth=2)
            ax.plot(x, k["estimate"], "o", color=color, markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=name)
        title = "quiz (true effect)" if action == "quiz" else "resource (no effect)"
        style(ax, title, "estimate before the cohort")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_xticks(sorted(rows["cohort"].unique()))
        ax.yaxis.set_major_formatter(lambda v, _: f"{v * 100:+.0f} pp" if round(v, 4) else "0")
    axes[0].set_ylabel("effect of one week of use on pass", color=TEXT_SECONDARY, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=TEXT_SECONDARY, loc="upper left")
    fig.text(0.01, 0.01, "Hidden confounder world. Lines: 95% range. The observational lift "
             "rates resource too high. The experimental effect does not.",
             color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
