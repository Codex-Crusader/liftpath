"""Live mode (BUILD2 Phase D): a small sqlite store, live states, advice and table refresh.

The live store holds demo students only. Their outcomes feed the live lift tables after
refresh_tables, the same way train outcomes feed the app tables.
"""

import os
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import LEVELS, lift_tables, point_lifts
from liftpath.paths import APP_DIR, DATA_DIR
from liftpath.privacy import suppress_counts
from liftpath.recommend import State, recommend
from liftpath.sim import make_explore
from liftpath.states import NONE_BAND, PASS_RESULTS, TERTILES, action_of, score_bands

LIVE_ENV = "LIVE_DATA_DIR"
GOALS = ("goal_pass", "goal_distinction")
COUNT_COLS = ["n_did", "n_did_not"]
CUTOFF_FILE = "effort_cutoffs.parquet"
LIVE_PREFIX = "LIVE_"
EXPLORE = "explore"
# No experimental effects in live mode: explore uses the observational rows only.
NO_EXPERIMENT = pd.DataFrame(columns=["action", "available", "effect", "ci_low", "ci_high"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(student_id TEXT PRIMARY KEY, module TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS activity(student_id TEXT, week INTEGER, item_type TEXT,
                                    clicks INTEGER);
CREATE TABLE IF NOT EXISTS scores(student_id TEXT, assessment_no INTEGER, week INTEGER,
                                  score REAL);
CREATE TABLE IF NOT EXISTS advice(student_id TEXT, week INTEGER, status TEXT, action TEXT,
                                  explored INTEGER, lift REAL, ci_low REAL, ci_high REAL,
                                  created TEXT);
CREATE TABLE IF NOT EXISTS outcomes(student_id TEXT PRIMARY KEY, final_result TEXT);
"""


def live_dir() -> Path:
    """The live data folder. Read at call time, so tests can point it at a temp folder."""
    return Path(os.environ.get(LIVE_ENV, str(DATA_DIR / "live")))


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_table(path: Path) -> pd.DataFrame:
    """Read a lift table. Suppressed counts are NULL. Floats keep the support rule safe."""
    table = pd.read_parquet(path)
    for col in [c for c in COUNT_COLS if c in table]:
        table[col] = table[col].astype(float)
    return table


def live_tables_exist(goal: str, folder: Path | None = None) -> bool:
    folder = folder or live_dir()
    return all((folder / "tables" / f"{goal}_level{lv}.parquet").exists() for lv in LEVELS)


def load_lift_tables(goal: str, app_dir: Path = APP_DIR,
                     folder: Path | None = None) -> dict[int, pd.DataFrame]:
    """The live tables when all of them exist, else the app tables."""
    folder = folder or live_dir()
    folder = folder / "tables" if live_tables_exist(goal, folder) else app_dir
    return {lv: read_table(folder / f"{goal}_level{lv}.parquet") for lv in LEVELS}


def effort_cutoffs(train: pd.DataFrame) -> pd.DataFrame:
    """Per (module, week): the tertile cutoffs of clicks_week > 0 and the usual week_block.

    Training bands rank within (course_id, week). Live mode pools the presentations of a module.
    """
    active = train[train["clicks_week"] > 0]
    cuts = active.groupby(["module", "week"])["clicks_week"].quantile(list(TERTILES)).unstack()
    cuts.columns = ["low_max", "mid_max"]
    block = (train.groupby(["module", "week"])["week_block"]
             .agg(lambda s: s.value_counts().idxmax()).rename("week_block"))
    return pd.concat([cuts, block], axis=1).dropna(subset=["week_block"]).reset_index()


def band_effort(clicks: np.ndarray, low_max: np.ndarray, mid_max: np.ndarray) -> np.ndarray:
    """Effort band from clicks and the cutoffs. A missing cutoff (no active student) is high."""
    return np.select([clicks <= 0, clicks <= low_max, clicks <= mid_max],
                     [NONE_BAND, "low", "mid"], "high")


def cutoff_row(cutoffs: pd.DataFrame, module: str, week: int) -> pd.Series:
    rows = cutoffs[(cutoffs["module"] == module) & (cutoffs["week"] == week)]
    if rows.empty:
        raise ValueError(f"No past data for module {module} at week {week}.")
    return rows.iloc[0]


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    # Demo store: fewer disk syncs per commit. A crash can lose the last few writes.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def add_student(con: sqlite3.Connection, student_id: str, module: str) -> None:
    con.execute("INSERT OR REPLACE INTO students VALUES (?, ?, ?)", (student_id, module, now()))
    con.commit()


def log_activity(con: sqlite3.Connection, student_id: str, week: int, item_type: str,
                 clicks: int) -> None:
    con.execute("INSERT INTO activity VALUES (?, ?, ?, ?)",
                (student_id, int(week), item_type, int(clicks)))
    con.commit()


def log_score(con: sqlite3.Connection, student_id: str, assessment_no: int, week: int,
              score: float) -> None:
    con.execute("INSERT INTO scores VALUES (?, ?, ?, ?)",
                (student_id, int(assessment_no), int(week), float(score)))
    con.commit()


def set_outcome(con: sqlite3.Connection, student_id: str, final_result: str) -> None:
    con.execute("INSERT OR REPLACE INTO outcomes VALUES (?, ?)", (student_id, final_result))
    con.commit()


def student_module(con: sqlite3.Connection, student_id: str) -> str:
    row = con.execute("SELECT module FROM students WHERE student_id = ?",
                      (student_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown student {student_id}.")
    return row[0]


def live_state(con: sqlite3.Connection, student_id: str, week: int, cutoffs: pd.DataFrame,
               cfg: Config) -> State:
    """The SPEC section 7 state at week w. It uses only data with week <= w."""
    module = student_module(con, student_id)
    cut = cutoff_row(cutoffs, module, week)
    (clicks,) = con.execute("SELECT COALESCE(sum(clicks), 0) FROM activity "
                            "WHERE student_id = ? AND week = ?", (student_id, week)).fetchone()
    n, total = con.execute("SELECT count(score), COALESCE(sum(score), 0) FROM scores "
                           "WHERE student_id = ? AND week <= ?", (student_id, week)).fetchone()
    effort = band_effort(np.array([clicks]), np.array([cut["low_max"]]),
                         np.array([cut["mid_max"]]))[0]
    score = score_bands(np.array([n]), np.array([total], dtype=float), cfg)[0]
    return State(module, cut["week_block"], str(score), str(effort))


def advise(con: sqlite3.Connection, student_id: str, week: int, goal: str,
           tables: dict[int, pd.DataFrame], candidates: list[str], cutoffs: pd.DataFrame,
           cfg: Config, rng: np.random.Generator) -> dict:
    """Advice for week w + 1. A share sim_explore_share of decisions explores (SPEC sim rule).

    The caller owns rng, so repeated calls draw new numbers.
    """
    state = live_state(con, student_id, week, cutoffs, cfg)
    point = pd.DataFrame([asdict(state)])
    actions, explored = make_explore(tables, NO_EXPERIMENT, candidates, cfg, rng)(point, week)
    if explored[0]:
        action = actions.iloc[0]
        rows = point_lifts(point, tables, cfg)
        rows = rows[rows["action"] == action]
        est = rows.iloc[0] if len(rows) else None
        status = EXPLORE
        lift, low, high = ((float(est["lift"]), float(est["ci_low"]), float(est["ci_high"]))
                           if est is not None else (None, None, None))
    else:
        rec = recommend(state, goal, tables, cfg)
        status, e = rec.status, rec.estimate
        action = e.action if e else None
        lift, low, high = (e.lift, e.ci_low, e.ci_high) if e else (None, None, None)
    advice = {"student_id": student_id, "week": int(week), "status": status, "action": action,
              "explored": int(bool(explored[0])), "lift": lift, "ci_low": low,
              "ci_high": high, "created": now()}
    con.execute("INSERT INTO advice VALUES (:student_id, :week, :status, :action, :explored, "
                ":lift, :ci_low, :ci_high, :created)", advice)
    con.commit()
    return {**advice, "state": asdict(state)}


def live_points(con: sqlite3.Connection, candidates: list[str], cutoffs: pd.DataFrame,
                cfg: Config) -> pd.DataFrame:
    """Decision points of live students with an outcome, for every week w that has a w + 1."""
    students = pd.read_sql_query(
        "SELECT s.student_id, s.module, o.final_result FROM students s "
        "JOIN outcomes o USING (student_id)", con)
    activity = pd.read_sql_query("SELECT * FROM activity", con)
    scores = pd.read_sql_query("SELECT * FROM scores", con)
    activity = activity[activity["student_id"].isin(students["student_id"])]
    if students.empty or activity.empty:
        return pd.DataFrame()
    last = activity.groupby("student_id")["week"].max().rename("last_week")
    grid = students.merge(last, on="student_id")
    grid = grid.loc[grid.index.repeat(grid["last_week"].clip(lower=0))].reset_index(drop=True)
    grid["week"] = grid.groupby("student_id").cumcount()
    grid = grid.merge(cutoffs[["module", "week", "week_block"]], on=["module", "week"],
                      how="inner")

    activity["action"] = action_of(activity["item_type"], cfg)
    totals = activity.groupby(["student_id", "week"], as_index=False)["clicks"].sum()
    bounds = cutoffs[["module", "week", "low_max", "mid_max"]]
    for offset, col in ((0, "effort_band"), (1, "next_effort_band")):
        keys = grid[["student_id", "module"]].assign(week=grid["week"] + offset)
        rows = (keys.merge(totals, on=["student_id", "week"], how="left")
                .merge(bounds, on=["module", "week"], how="left"))
        grid[col] = band_effort(rows["clicks"].fillna(0).to_numpy(),
                                rows["low_max"].to_numpy(), rows["mid_max"].to_numpy())
    nxt = (activity[activity["clicks"] > 0].groupby(["student_id", "week", "action"])
           .size().unstack(fill_value=0).reindex(columns=candidates, fill_value=0) > 0)
    nxt = nxt.reset_index().assign(week=lambda d: d["week"] - 1)
    grid = grid.merge(nxt, on=["student_id", "week"], how="left")
    for action in candidates:
        grid[f"act_{action}"] = grid.pop(action).eq(True)

    known = (grid[["student_id", "week"]]
             .merge(scores, on="student_id", how="left").query("week_y <= week_x")
             .groupby(["student_id", "week_x"])["score"].agg(["count", "sum"]))
    known.index.names = ["student_id", "week"]
    grid = grid.merge(known.reset_index(), on=["student_id", "week"], how="left")
    grid["score_band"] = score_bands(grid["count"].fillna(0).to_numpy(),
                                     grid["sum"].fillna(0).to_numpy(), cfg)
    grid["course_id"] = LIVE_PREFIX + grid["module"]
    grid["split"] = "live"
    grid["goal_pass"] = grid["final_result"].isin(PASS_RESULTS)
    grid["goal_distinction"] = grid["final_result"] == "Distinction"
    columns = ["course_id", "module", "split", "student_id", "week", "week_block", "score_band",
               "effort_band", "next_effort_band", *[f"act_{a}" for a in candidates],
               "goal_pass", "goal_distinction"]
    return grid[columns]


def refresh_tables(con: sqlite3.Connection, train: pd.DataFrame, candidates: list[str],
                   cutoffs: pd.DataFrame, cfg: Config,
                   folder: Path | None = None) -> dict[str, dict[int, pd.DataFrame]]:
    """Append the live points to the train points, rebuild the lift tables and write them
    (with suppressed counts) to live_dir/tables. Return the unsuppressed tables."""
    if (train["split"] == "test").any():
        raise ValueError("Test points must not enter the live lift tables.")
    live = live_points(con, candidates, cutoffs, cfg)
    # Train ids are integers and live ids are text. One type keeps the student key sortable.
    points = pd.concat([train.assign(student_id=train["student_id"].astype(str)), live],
                       ignore_index=True)
    out = (folder or live_dir()) / "tables"
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for goal in GOALS:
        tables = lift_tables(points, candidates, goal, cfg)
        for level, table in tables.items():
            suppress_counts(table, COUNT_COLS, cfg).to_parquet(
                out / f"{goal}_level{level}.parquet", index=False)
        result[goal] = tables
    return result
