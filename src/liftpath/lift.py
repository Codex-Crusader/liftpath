"""Lift estimator and back-off levels (SPEC sections 7, 10 and 11)."""

import numpy as np
import pandas as pd

from liftpath.config import Config

LEVELS: dict[int, list[str]] = {
    0: ["module", "week_block", "score_band", "effort_band"],
    1: ["module", "score_band", "effort_band"],
    2: ["score_band", "effort_band"],
}
NONE_BAND = "none"
POOLED = "_pooled"
STUDENT_KEY = ["course_id", "student_id"]
RECOMMEND, NO_CLEAR_WINNER, ABSTAIN = "recommend", "no_clear_winner", "abstain"
ESTIMATE_COLS = ["lift", "ci_low", "ci_high", "p1_avg", "p0_avg", "n_did", "n_did_not"]


def estimate_lifts(points: pd.DataFrame, cell_cols: list[str], effort_col: str,
                   treatment_cols: list[str], goal_col: str, cfg: Config) -> pd.DataFrame:
    """Effort-matched lift of each treatment on the goal, per cell (SPEC section 10).

    Empty cell_cols gives one pooled cell. The action column holds the treatment column name.
    """
    m, z = cfg.prior_strength, cfg.z
    cells = list(cell_cols) or [POOLED]
    df = points.assign(**{POOLED: True}) if not cell_cols else points
    df = df.assign(_student=df.groupby(STUDENT_KEY).ngroup(), _goal=df[goal_col].astype(int))
    base = df.groupby(cells)["_goal"].mean().rename("base_rate")
    compared = df[df[effort_col] != NONE_BAND]

    parts = []
    for treatment in treatment_cols:
        groups = (compared.groupby([*cells, effort_col, treatment])
                  .agg(n=("_goal", "size"), k=("_goal", "sum"), u=("_student", "nunique"))
                  .unstack(treatment, fill_value=0))
        if True not in groups["n"].columns or False not in groups["n"].columns:
            continue
        bands = pd.DataFrame({
            "n1": groups[("n", True)], "k1": groups[("k", True)], "u1": groups[("u", True)],
            "n0": groups[("n", False)], "k0": groups[("k", False)], "u0": groups[("u", False)],
        })
        bands = bands[(bands["n1"] >= 1) & (bands["n0"] >= 1)].reset_index()
        bands = bands.merge(base.reset_index(), on=cells)
        p_c = bands["base_rate"]
        bands["p1"] = (bands["k1"] + m * p_c) / (bands["n1"] + m)
        bands["p0"] = (bands["k0"] + m * p_c) / (bands["n0"] + m)
        bands["w"] = bands["n1"] * bands["n0"] / (bands["n1"] + bands["n0"])
        bands["var"] = (bands["p1"] * (1 - bands["p1"]) / (bands["u1"] + m)
                        + bands["p0"] * (1 - bands["p0"]) / (bands["u0"] + m))
        bands = bands.assign(
            w_diff=bands["w"] * (bands["p1"] - bands["p0"]),
            w_p1=bands["w"] * bands["p1"], w_p0=bands["w"] * bands["p0"],
            w2_var=bands["w"] ** 2 * bands["var"])
        agg = bands.groupby(cells).agg(
            sum_w=("w", "sum"), w_diff=("w_diff", "sum"), w_p1=("w_p1", "sum"),
            w_p0=("w_p0", "sum"), w2_var=("w2_var", "sum"), n_did=("n1", "sum"),
            n_did_not=("n0", "sum"), base_rate=("base_rate", "first"))
        out = pd.DataFrame(index=agg.index)
        out["action"] = treatment
        out["lift"] = agg["w_diff"] / agg["sum_w"]
        out["se"] = np.sqrt(agg["w2_var"]) / agg["sum_w"]
        out["ci_low"] = out["lift"] - z * out["se"]
        out["ci_high"] = out["lift"] + z * out["se"]
        out["p1_avg"] = agg["w_p1"] / agg["sum_w"]
        out["p0_avg"] = agg["w_p0"] / agg["sum_w"]
        out["n_did"] = agg["n_did"].astype("int64")
        out["n_did_not"] = agg["n_did_not"].astype("int64")
        out["base_rate"] = agg["base_rate"]
        parts.append(out.reset_index())

    columns = [*cells, "action", "lift", "se", "ci_low", "ci_high", "p1_avg", "p0_avg",
               "n_did", "n_did_not", "base_rate"]
    table = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    table = table[columns]
    return table.drop(columns=POOLED) if not cell_cols else table


def lift_tables(points: pd.DataFrame, candidates: list[str], goal_col: str,
                cfg: Config) -> dict[int, pd.DataFrame]:
    """Lift per candidate at every back-off level, controlled for next_effort_band."""
    treatments = [f"act_{a}" for a in candidates]
    tables = {}
    for level, cells in LEVELS.items():
        table = estimate_lifts(points, cells, "next_effort_band", treatments, goal_col, cfg)
        table["action"] = table["action"].str.removeprefix("act_")
        tables[level] = table
    return tables


def best_actions(tables: dict[int, pd.DataFrame], cfg: Config) -> dict[int, pd.DataFrame]:
    """Per level, the decision for each cell that has a supported candidate (SPEC section 11).

    A cell is missing from the result when no candidate is supported; the caller backs off.
    """
    best = {}
    for level, table in tables.items():
        cells = LEVELS[level]
        supported = table[np.minimum(table["n_did"], table["n_did_not"]) >= cfg.min_count]
        status = (supported.assign(_win=supported["ci_low"] > 0)
                  .groupby(cells, as_index=False)["_win"].any())
        status["status"] = np.where(status.pop("_win"), RECOMMEND, NO_CLEAR_WINNER)
        winners = (supported[supported["ci_low"] > 0]
                   .sort_values([*cells, "lift", "action"],
                                ascending=[True] * len(cells) + [False, True])
                   .drop_duplicates(cells))
        best[level] = status.merge(winners[[*cells, "action", *ESTIMATE_COLS]], on=cells,
                                   how="left")
    return best


def resolve_points(points: pd.DataFrame, best: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Status, action, level and estimate for every point, with back-off from level 0 to 2.

    no_clear_winner stops the back-off. A point with no level gets abstain.
    """
    result = pd.DataFrame(index=points.index)
    result["status"] = ABSTAIN
    result["level"] = pd.array([pd.NA] * len(points), dtype="Int64")
    result["action"] = pd.Series([None] * len(points), index=points.index, dtype=object)
    for col in ESTIMATE_COLS:
        result[col] = np.nan
    open_rows = pd.Series(True, index=points.index)
    for level in sorted(best):
        cells = LEVELS[level]
        todo = points.loc[open_rows, cells].rename_axis("_row").reset_index()
        found = todo.merge(best[level], on=cells, how="inner").set_index("_row")
        if found.empty:
            continue
        result.loc[found.index, "status"] = found["status"]
        result.loc[found.index, "level"] = level
        result.loc[found.index, "action"] = found["action"]
        result.loc[found.index, ESTIMATE_COLS] = found[ESTIMATE_COLS].astype(float)
        open_rows.loc[found.index] = False
    result["action"] = result["action"].astype(object).where(result["action"].notna(), None)
    return result
