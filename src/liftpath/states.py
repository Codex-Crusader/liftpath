"""Decision points, states, actions and goals (SPEC sections 5 to 9 and 18).

build_decision_points and select_candidates expect a connection where
register_canonical already created one view per canonical table.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import LEVELS
from liftpath.schema import CANONICAL

WEEK_DAYS = 7
# Tertile cuts for week_block and for the effort percentile (SPEC section 7).
TERTILES = (1 / 3, 2 / 3)
NONE_BAND = "none"
KEY = ["course_id", "student_id"]
PASS_RESULTS = ("Pass", "Distinction")

FALLBACK_GROUPS: dict[str, list[str]] = {
    "reading": ["oucontent", "resource", "url", "subpage", "page", "folder", "dualpane",
                "sharedsubpage", "htmlactivity", "dataplus"],
    "practice": ["quiz", "externalquiz", "questionnaire", "repeatactivity"],
    "discussion": ["forumng", "ouwiki", "glossary"],
    "live": ["oucollaborate", "ouelluminate"],
    "navigation": ["homepage"],
}
GROUP_OF = {item: group for group, items in FALLBACK_GROUPS.items() for item in items}


def register_canonical(con: duckdb.DuckDBPyConnection, folder: Path) -> None:
    """Create a view per canonical table, plus course_split (SPEC section 5)."""
    for table in CANONICAL:
        path = (folder / f"{table}.parquet").as_posix()
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{path}')")
    con.execute(
        """CREATE OR REPLACE VIEW course_split AS
           SELECT course_id, module, presentation, length_days,
                  CASE WHEN count(*) OVER (PARTITION BY module) > 1
                        AND presentation = max(presentation) OVER (PARTITION BY module)
                       THEN 'test' ELSE 'train' END AS split
           FROM courses"""
    )


def single_presentation_modules(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT module FROM courses GROUP BY module HAVING count(*) = 1 ORDER BY module"
    ).fetchall()
    return [row[0] for row in rows]


def action_of(item_types: pd.Series, cfg: Config) -> pd.Series:
    """Map item types to actions. With fallback groups, a type becomes its group."""
    if not cfg.use_fallback_groups:
        return item_types
    return item_types.map(GROUP_OF).fillna(item_types)


def excluded_actions(cfg: Config) -> set[str]:
    return set(action_of(pd.Series(list(cfg.exclude_types), dtype=object), cfg))


def select_candidates(con: duckdb.DuckDBPyConnection, cfg: Config) -> list[str]:
    totals = con.execute(
        """SELECT i.item_type, sum(e.clicks) AS clicks
           FROM events e
           JOIN items i USING (course_id, item_id)
           JOIN course_split s USING (course_id)
           WHERE s.split = 'train'
           GROUP BY i.item_type"""
    ).df()
    totals["action"] = action_of(totals["item_type"], cfg)
    totals = totals[~totals["action"].isin(excluded_actions(cfg))]
    ranked = (totals.groupby("action", as_index=False)["clicks"].sum()
              .sort_values(["clicks", "action"], ascending=[False, True]))
    return ranked["action"].head(cfg.n_candidates).tolist()


def weekly_clicks(con: duckdb.DuckDBPyConnection, cfg: Config) -> pd.DataFrame:
    """Clicks per (course_id, student_id, week, action). Weeks before day 0 are negative."""
    weekly = con.execute(
        f"""SELECT e.course_id, e.student_id,
                   CAST(floor(e.day / {WEEK_DAYS}) AS BIGINT) AS week,
                   i.item_type, sum(e.clicks) AS clicks
            FROM events e JOIN items i USING (course_id, item_id)
            GROUP BY ALL"""
    ).df()
    weekly["action"] = action_of(weekly["item_type"], cfg)
    return weekly.groupby([*KEY, "week", "action"], as_index=False)["clicks"].sum()


def decision_grid(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per enrollment and decision week w = 0 .. n_weeks - 2, before the
    registration filter."""
    enr = con.execute(
        f"""SELECT e.course_id, s.module, s.presentation, s.split, e.student_id,
                  e.reg_day, e.unreg_day, e.final_result,
                  CAST(ceil(s.length_days / {WEEK_DAYS}) AS BIGINT) AS n_weeks
           FROM enrollments e JOIN course_split s USING (course_id)"""
    ).df()
    n_decisions = (enr["n_weeks"] - 1).clip(lower=0)
    grid = enr.loc[enr.index.repeat(n_decisions)].reset_index(drop=True)
    grid["week"] = grid.groupby(KEY).cumcount()
    return grid


def effort_bands(totals: pd.DataFrame) -> pd.Series:
    """Band clicks > 0 by percentile rank within (course_id, week) (SPEC section 7)."""
    pct = totals.groupby(["course_id", "week"])["clicks"].rank(method="average", pct=True)
    return pd.Series(np.select([pct <= TERTILES[0], pct <= TERTILES[1]], ["low", "mid"], "high"),
                     index=totals.index)


def wide_by_action(weekly: pd.DataFrame, actions: list[str]) -> pd.DataFrame:
    """Clicks per (course_id, student_id, week) with one column per action, plus total."""
    total = weekly.groupby([*KEY, "week"])["clicks"].sum().rename("total")
    per_action = (weekly[weekly["action"].isin(actions)]
                  .pivot_table(index=[*KEY, "week"], columns="action", values="clicks",
                               aggfunc="sum", fill_value=0)
                  .reindex(columns=actions, fill_value=0))
    return pd.concat([total, per_action], axis=1).fillna(0).reset_index()


def add_effort(grid: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    totals = (weekly[weekly["week"] >= 0]
              .groupby([*KEY, "week"], as_index=False)["clicks"].sum())
    totals = totals[totals["clicks"] > 0]
    totals["band"] = effort_bands(totals)
    for offset, clicks_col, band_col in ((0, "clicks_week", "effort_band"),
                                         (1, "clicks_next", "next_effort_band")):
        shifted = totals.assign(week=totals["week"] - offset).rename(
            columns={"clicks": clicks_col, "band": band_col})
        grid = grid.merge(shifted, on=[*KEY, "week"], how="left")
        grid[clicks_col] = grid[clicks_col].fillna(0).astype("int64")
        grid[band_col] = grid[band_col].fillna(NONE_BAND)
    return grid


def add_actions(grid: pd.DataFrame, weekly: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    """act_<a>: clicks > 0 on action a in week w + 1 (SPEC section 8)."""
    nxt = wide_by_action(weekly[weekly["week"] >= 0], candidates).drop(columns="total")
    nxt["week"] -= 1
    grid = grid.merge(nxt, on=[*KEY, "week"], how="left")
    for action in candidates:
        grid[f"act_{action}"] = grid.pop(action).fillna(0) > 0
    return grid


def add_cum_shares(grid: pd.DataFrame, weekly: pd.DataFrame,
                   candidates: list[str]) -> pd.DataFrame:
    """cum_share_<a> over all days <= week_end(w). Clicks before day 0 count from week 0."""
    early = weekly.assign(week=weekly["week"].clip(lower=0))
    wide = wide_by_action(early, candidates)
    cum = grid[[*KEY, "week"]].merge(wide, on=[*KEY, "week"], how="left").fillna(0)
    cols = ["total", *candidates]
    cum[cols] = cum.groupby(KEY)[cols].cumsum()
    total = cum["total"].to_numpy()
    for action in candidates:
        share = np.divide(cum[action].to_numpy(), total, out=np.zeros(len(cum)),
                          where=total > 0)
        grid[f"cum_share_{action}"] = share
    return grid


def add_score_band(grid: pd.DataFrame, con: duckdb.DuckDBPyConnection,
                   cfg: Config) -> pd.DataFrame:
    """Mean non-Exam score known by week_end(w). known_day = max(submit_day, due_day)."""
    subs = con.execute(
        f"""SELECT s.course_id, s.student_id, s.score,
                   CAST(floor(CASE WHEN a.due_day IS NULL THEN s.submit_day
                                   WHEN s.submit_day IS NULL THEN a.due_day
                                   ELSE greatest(s.submit_day, a.due_day) END
                              / {WEEK_DAYS}) AS BIGINT) AS week
            FROM submissions s JOIN assessments a USING (course_id, assessment_id)
            WHERE a.kind <> 'Exam' AND s.score IS NOT NULL"""
    ).df().dropna(subset=["week"])
    subs["week"] = subs["week"].astype("int64").clip(lower=0)
    per_week = subs.groupby([*KEY, "week"], as_index=False).agg(
        score_sum=("score", "sum"), score_n=("score", "size"))
    cum = grid[[*KEY, "week"]].merge(per_week, on=[*KEY, "week"], how="left").fillna(0)
    cum[["score_sum", "score_n"]] = cum.groupby(KEY)[["score_sum", "score_n"]].cumsum()
    n = cum["score_n"].to_numpy()
    mean = np.divide(cum["score_sum"].to_numpy(), n, out=np.zeros(len(cum)), where=n > 0)
    grid["score_band"] = np.select(
        [n == 0, mean < cfg.score_low_max, mean < cfg.score_mid_max],
        [NONE_BAND, "low", "mid"], "high")
    return grid


def add_week_block(grid: pd.DataFrame) -> pd.DataFrame:
    w, n = grid["week"], grid["n_weeks"]
    grid["week_block"] = np.select([w < n * TERTILES[0], w < n * TERTILES[1]],
                                   ["early", "mid"], "late")
    return grid


def registered(grid: pd.DataFrame) -> pd.Series:
    """Registered at week_end(w) = 7w + 6 (SPEC section 6)."""
    week_end = WEEK_DAYS * grid["week"] + WEEK_DAYS - 1
    reg_ok = grid["reg_day"].isna() | (grid["reg_day"] <= week_end)
    unreg_ok = grid["unreg_day"].isna() | (grid["unreg_day"] > week_end)
    return reg_ok & unreg_ok


def build_decision_points(con: duckdb.DuckDBPyConnection, cfg: Config,
                          candidates: list[str]) -> pd.DataFrame:
    weekly = weekly_clicks(con, cfg)
    grid = decision_grid(con)
    # Cumulative features run over every week before the registration filter,
    # so a late registrant keeps scores and clicks from before registration.
    grid = add_week_block(grid)
    grid = add_score_band(grid, con, cfg)
    grid = add_effort(grid, weekly)
    grid = add_cum_shares(grid, weekly, candidates)
    grid = add_actions(grid, weekly, candidates)
    grid["goal_pass"] = grid["final_result"].isin(PASS_RESULTS)
    grid["goal_distinction"] = grid["final_result"] == "Distinction"
    grid = grid[registered(grid)].reset_index(drop=True)
    columns = [
        "course_id", "module", "presentation", "split", "student_id", "week", "week_block",
        "score_band", "effort_band", "next_effort_band", "clicks_week", "clicks_next",
        *[f"cum_share_{a}" for a in candidates], *[f"act_{a}" for a in candidates],
        "goal_pass", "goal_distinction",
    ]
    return grid[columns]


def check_variety(points: pd.DataFrame, candidates: list[str], cfg: Config) -> pd.DataFrame:
    """Per candidate: the share of train points in level 0 cells where n_did and n_did_not
    both reach min_count. n_did and n_did_not use the SPEC section 10 band rules."""
    train = points[points["split"] == "train"]
    cell = LEVELS[0]
    cell_sizes = train.groupby(cell).size()
    compared = train[train["next_effort_band"] != NONE_BAND]
    rows = []
    for action in candidates:
        bands = compared.groupby([*cell, "next_effort_band"])[f"act_{action}"].agg(
            n1="sum", n="size")
        bands["n0"] = bands["n"] - bands["n1"]
        bands = bands[(bands["n1"] >= 1) & (bands["n0"] >= 1)]
        per_cell = bands.groupby(level=cell)[["n1", "n0"]].sum()
        supported = per_cell[(per_cell["n1"] >= cfg.min_count)
                             & (per_cell["n0"] >= cfg.min_count)].index
        covered = cell_sizes[cell_sizes.index.isin(supported)].sum()
        rows.append({"candidate": action, "share": covered / len(train),
                     "supported_cells": len(supported), "cells": len(cell_sizes)})
    variety = pd.DataFrame(rows)
    variety["passes"] = variety["share"] >= cfg.gate_variety_min_share
    return variety


def gate1_passes(variety: pd.DataFrame, cfg: Config) -> bool:
    return int(variety["passes"].sum()) >= cfg.gate_variety_min_candidates


def variety_report(variety: pd.DataFrame, cfg: Config, n_train: int) -> str:
    lines = [
        f"# Gate 1: variety ({cfg.scope} scope)",
        "",
        f"Train points: {n_train:,}. min_count: {cfg.min_count}. "
        f"Fallback groups: {cfg.use_fallback_groups}.",
        "",
        "| candidate | share of train points | supported cells | cells | passes |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {r.candidate} | {r.share:.3f} | {r.supported_cells} | {r.cells} | "
              f"{'yes' if r.passes else 'no'} |" for r in variety.itertuples()]
    result = "PASS" if gate1_passes(variety, cfg) else "FAIL"
    lines += ["", f"Gate 1: {result}. {int(variety['passes'].sum())} candidates have share "
              f">= {cfg.gate_variety_min_share}. The gate needs "
              f"{cfg.gate_variety_min_candidates}."]
    return "\n".join(lines) + "\n"
