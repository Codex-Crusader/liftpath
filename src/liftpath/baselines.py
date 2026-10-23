"""Recommenders to compare (SPEC section 14). Each maps test points to one action or None."""

from collections.abc import Callable

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import LEVELS, RECOMMEND, best_actions, resolve_points

Recommender = Callable[[pd.DataFrame], pd.Series]
CF_CHUNK_ROWS = 2000


def act_cols(candidates: list[str]) -> list[str]:
    return [f"act_{a}" for a in candidates]


def as_actions(actions: pd.Series) -> pd.Series:
    """Missing actions as None, not NaN."""
    return actions.astype(object).where(actions.notna(), None)


def best_by_cell(scores: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    """The candidate with the highest score per cell. NaN scores never win. Ties go to the
    first candidate in candidate order."""
    scores = scores.set_axis(candidates, axis=1).dropna(how="all")
    if scores.empty:
        return pd.DataFrame(columns=[*scores.index.names, "action"])
    return scores.idxmax(axis=1).rename("action").reset_index()


def lookup(points: pd.DataFrame, choices: list[tuple[list[str], pd.DataFrame]]) -> pd.Series:
    """Look up the action per point, trying each (cells, table) pair in order."""
    actions = pd.Series(None, index=points.index, dtype=object)
    for cells, table in choices:
        todo = points.loc[actions.isna(), cells].rename_axis("_row").reset_index()
        found = todo.merge(table, on=cells, how="inner").set_index("_row")["action"]
        actions.loc[found.index] = found
    return as_actions(actions)


def make_random(candidates: list[str], seed: int) -> Recommender:
    def recommend(points: pd.DataFrame) -> pd.Series:
        rng = np.random.default_rng(seed)
        picks = rng.choice(np.array(candidates, dtype=object), len(points))
        return pd.Series(picks, index=points.index, dtype=object)
    return recommend


def make_popular(train: pd.DataFrame, candidates: list[str], cfg: Config) -> Recommender:
    """Most used candidate next week in the same level 0 cell. A cell with fewer than
    min_count train points backs off to the next level."""
    choices = []
    for cells in LEVELS.values():
        groups = train.groupby(cells)
        scores = groups[act_cols(candidates)].mean()
        scores = scores[groups.size() >= cfg.min_count]
        choices.append((cells, best_by_cell(scores, candidates)))
    return lambda points: lookup(points, choices)


def make_course_order(train: pd.DataFrame, candidates: list[str]) -> Recommender:
    """Most used candidate next week in the same (module, week). An unseen pair gets None."""
    cells = ["module", "week"]
    scores = train.groupby(cells)[act_cols(candidates)].mean()
    choices = [(cells, best_by_cell(scores, candidates))]
    return lambda points: lookup(points, choices)


def make_raw_success(train: pd.DataFrame, candidates: list[str], goal_col: str,
                     cfg: Config) -> Recommender:
    """Highest P(goal | cell, act = true) with n1 >= min_count, with back-off. No effort
    control and no comparison group."""
    acts = train[act_cols(candidates)]
    reached = acts.mul(train[goal_col], axis=0)
    choices = []
    for cells in LEVELS.values():
        n1 = acts.groupby([train[c] for c in cells]).sum()
        k1 = reached.groupby([train[c] for c in cells]).sum()
        scores = (k1 / n1).where(n1 >= cfg.min_count)
        choices.append((cells, best_by_cell(scores, candidates)))
    return lambda points: lookup(points, choices)


def unit_rows(x: np.ndarray) -> np.ndarray:
    """Scale rows to length 1. A zero row stays zero, so its cosine similarity is 0."""
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    return np.divide(x, norm, out=np.zeros_like(x), where=norm > 0)


def make_user_cf(train: pd.DataFrame, candidates: list[str], cfg: Config) -> Recommender:
    """Most used candidate next week among the cf_neighbors most similar train points in the
    same (module, week), by cosine similarity of cum_share_<a>."""
    share_cols = [f"cum_share_{a}" for a in candidates]
    groups = {key: (unit_rows(g[share_cols].to_numpy(float)),
                    g[act_cols(candidates)].to_numpy(float))
              for key, g in train.groupby(["module", "week"])}

    def recommend(points: pd.DataFrame) -> pd.Series:
        actions = pd.Series(None, index=points.index, dtype=object)
        for key, test in points.groupby(["module", "week"]):
            if key not in groups:
                continue
            shares, acts = groups[key]
            k = min(cfg.cf_neighbors, len(shares))
            query = unit_rows(test[share_cols].to_numpy(float))
            picks = []
            for start in range(0, len(query), CF_CHUNK_ROWS):
                sim = query[start:start + CF_CHUNK_ROWS] @ shares.T
                nearest = np.argpartition(-sim, k - 1, axis=1)[:, :k]
                picks.append(acts[nearest].mean(axis=1).argmax(axis=1))
            actions.loc[test.index] = np.array(candidates, dtype=object)[np.concatenate(picks)]
        return as_actions(actions)
    return recommend


def make_liftpath(tables: dict[int, pd.DataFrame], goal_col: str, cfg: Config) -> Recommender:
    """SPEC section 11. Only status recommend gives an action."""
    best = best_actions(tables, cfg)

    def recommend(points: pd.DataFrame) -> pd.Series:
        resolved = resolve_points(points, best)
        return as_actions(resolved["action"].where(resolved["status"] == RECOMMEND))
    return recommend
