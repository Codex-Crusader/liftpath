"""Follower lift with a student cluster bootstrap (SPEC section 15).

Every recommender uses the same bootstrap draws, so net lift (R minus random) gets a paired
interval.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from liftpath.baselines import Recommender
from liftpath.config import Config
from liftpath.lift import LEVELS, NONE_BAND, STUDENT_KEY

STRATUM_COLS = [*LEVELS[0], "next_effort_band"]
BASELINE = "random"


@dataclass(frozen=True)
class EvalResult:
    name: str
    coverage: float
    lift: float
    ci_low: float
    ci_high: float
    n_points: int


def student_index(points: pd.DataFrame) -> np.ndarray:
    return points.groupby(STUDENT_KEY).ngroup().to_numpy()


def student_draws(n_students: int, cfg: Config, rng: np.random.Generator) -> np.ndarray:
    """Per bootstrap run, how many times each student is drawn (with replacement)."""
    picks = rng.integers(0, n_students, (cfg.n_boot, n_students))
    return np.stack([np.bincount(row, minlength=n_students) for row in picks])


def lift_from_counts(nf, kf, nn, kn) -> np.ndarray:
    """SPEC section 15 follower lift. The last axis is the stratum."""
    valid = (nf > 0) & (nn > 0)
    pf = np.divide(kf, nf, out=np.zeros_like(kf, dtype=float), where=valid)
    pn = np.divide(kn, nn, out=np.zeros_like(kn, dtype=float), where=valid)
    w = np.where(valid, nf * nn / np.where(valid, nf + nn, 1), 0.0)
    total = w.sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (w * (pf - pn)).sum(axis=-1) / total


def follower_flags(points: pd.DataFrame, actions: pd.Series) -> np.ndarray:
    """True where the student used the recommended action next week."""
    has = actions.notna().to_numpy()
    flags = np.zeros(len(points), dtype=bool)
    for action in actions[has].unique():
        rows = (actions == action).to_numpy()
        flags[rows] = points.loc[rows, f"act_{action}"].to_numpy(bool)
    return flags


def follower_boot(points: pd.DataFrame, actions: pd.Series, goal_col: str,
                  students: np.ndarray, draws: np.ndarray) -> tuple[float, np.ndarray]:
    """Point estimate and bootstrap values of follower lift."""
    keep = (actions.notna() & (points["next_effort_band"] != NONE_BAND)).to_numpy()
    if not keep.any():
        return np.nan, np.full(len(draws), np.nan)
    sub = points.loc[keep, STRATUM_COLS].copy()
    sub["_student"] = students[keep]
    sub["_follow"] = follower_flags(points, actions)[keep]
    sub["_goal"] = points.loc[keep, goal_col].to_numpy(int)
    cells = (sub.groupby(["_student", *STRATUM_COLS, "_follow"], observed=True)["_goal"]
             .agg(["size", "sum"]).reset_index())
    stratum = cells.groupby(STRATUM_COLS, observed=True).ngroup().to_numpy()
    n_strata = stratum.max() + 1
    follow = cells["_follow"].to_numpy()
    size, hits = cells["size"].to_numpy(float), cells["sum"].to_numpy(float)

    def counts(weights):
        return [np.bincount(stratum, weights=weights * v * m, minlength=n_strata)
                for m in (follow, ~follow) for v in (size, hits)]

    nf, kf, nn, kn = counts(np.ones(len(cells)))
    estimate = float(lift_from_counts(nf, kf, nn, kn))
    boots = np.array([lift_from_counts(*counts(row[cells["_student"].to_numpy()]))
                      for row in draws])
    return estimate, boots


def interval(boots: np.ndarray, cfg: Config) -> tuple[float, float]:
    """Percentile interval with the coverage that z gives (z = 1.96 gives 95%)."""
    tail = 100 * (1 - norm.cdf(cfg.z))
    values = boots[~np.isnan(boots)]
    if len(values) == 0:
        return np.nan, np.nan
    low, high = np.percentile(values, [tail, 100 - tail])
    return float(low), float(high)


def follower_lift(points: pd.DataFrame, actions: pd.Series, goal_col: str,
                  cfg: Config, rng: np.random.Generator) -> EvalResult:
    students = student_index(points)
    draws = student_draws(students.max() + 1, cfg, rng)
    estimate, boots = follower_boot(points, actions, goal_col, students, draws)
    low, high = interval(boots, cfg)
    return EvalResult(name="", coverage=float(actions.notna().mean()), lift=estimate,
                      ci_low=low, ci_high=high, n_points=int(actions.notna().sum()))


def evaluate_all(test: pd.DataFrame, recommenders: dict[str, Recommender],
                 goal_col: str, cfg: Config) -> pd.DataFrame:
    """All metrics per recommender, on all test points and on the common subset.

    The common subset is the test points where every recommender gives an action.
    """
    students = student_index(test)
    draws = student_draws(students.max() + 1, cfg, np.random.default_rng(cfg.seed))
    actions = {name: rec(test) for name, rec in recommenders.items()}
    common = np.logical_and.reduce([a.notna().to_numpy() for a in actions.values()])

    boots, rows = {}, {}
    for scope, mask in (("all", np.ones(len(test), dtype=bool)), ("common", common)):
        for name, act in actions.items():
            act = act.where(mask, None)
            estimate, boots[scope, name] = follower_boot(test, act, goal_col, students, draws)
            low, high = interval(boots[scope, name], cfg)
            rows[scope, name] = {"lift": estimate, "ci_low": low, "ci_high": high,
                                 "coverage": float(act.notna().mean()),
                                 "n_points": int(act.notna().sum())}

    table = []
    for name in actions:
        row = {"name": name}
        for scope in ("all", "common"):
            prefix = "" if scope == "all" else "common_"
            row.update({f"{prefix}{k}": v for k, v in rows[scope, name].items()})
            base = rows[scope, BASELINE]["lift"]
            net_low, net_high = interval(boots[scope, name] - boots[scope, BASELINE], cfg)
            row.update({f"{prefix}net_lift": rows[scope, name]["lift"] - base,
                        f"{prefix}net_ci_low": net_low, f"{prefix}net_ci_high": net_high})
        table.append(row)
    return pd.DataFrame(table)
