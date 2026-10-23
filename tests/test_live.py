"""Live mode and engine CLI (BUILD2 Phase D)."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.engine import dumps
from liftpath.lift import lift_tables
from liftpath.live import (
    add_student,
    advise,
    init_db,
    live_points,
    live_state,
    live_tables_exist,
    load_lift_tables,
    log_activity,
    log_score,
    refresh_tables,
    set_outcome,
)

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ["quiz", "forumng", "resource"]
WEEKS = 6


def strict_loads(text: str):
    def reject(name):
        raise ValueError(f"not valid JSON: {name}")
    return json.loads(text, parse_constant=reject)


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "config.yaml")


@pytest.fixture(scope="module")
def cutoffs():
    return pd.DataFrame({"module": "AAA", "week": range(WEEKS), "low_max": 10.0,
                         "mid_max": 30.0, "week_block": "early"})


def fill_students(con, n: int, seed: int, prefix: str) -> None:
    """n students of module AAA. Quiz users pass more often. Bulk inserts keep it fast."""
    rng = np.random.default_rng(seed)
    students, activity, scores, outcomes = [], [], [], []
    for i in range(n):
        sid = f"{prefix}{i}"
        students.append((sid, "AAA", "t"))
        quiz_weeks = 0
        for week in range(WEEKS):
            for item_type in CANDIDATES:
                if rng.random() < 0.5:
                    activity.append((sid, week, item_type, int(rng.integers(1, 40))))
                    quiz_weeks += item_type == "quiz"
        scores.append((sid, 1, 2, float(rng.integers(30, 100))))
        outcomes.append((sid, "Pass" if rng.random() < 0.2 + 0.1 * quiz_weeks else "Fail"))
    for table, rows in (("students", students), ("activity", activity), ("scores", scores),
                        ("outcomes", outcomes)):
        marks = ", ".join("?" * len(rows[0]))
        con.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    con.commit()


def expected_points(con) -> int:
    """One point per week w that has a week w + 1: the last active week per student."""
    (n,) = con.execute("SELECT sum(last) FROM (SELECT max(week) AS last FROM activity a "
                       "JOIN outcomes USING (student_id) GROUP BY student_id)").fetchone()
    return n


def test_db_round_trip(tmp_path):
    path = tmp_path / "live.db"
    con = init_db(path)
    add_student(con, "s1", "AAA")
    log_activity(con, "s1", 0, "quiz", 5)
    log_score(con, "s1", 1, 0, 72.5)
    set_outcome(con, "s1", "Pass")
    con.close()
    con = init_db(path)
    assert con.execute("SELECT student_id, module FROM students").fetchall() == [("s1", "AAA")]
    assert con.execute("SELECT * FROM activity").fetchall() == [("s1", 0, "quiz", 5)]
    assert con.execute("SELECT * FROM scores").fetchall() == [("s1", 1, 0, 72.5)]
    assert con.execute("SELECT * FROM outcomes").fetchall() == [("s1", "Pass")]


def test_state_follows_band_rules(tmp_path, cfg, cutoffs):
    con = init_db(tmp_path / "live.db")
    add_student(con, "s1", "AAA")
    state = live_state(con, "s1", 0, cutoffs, cfg)
    assert (state.effort_band, state.score_band, state.week_block) == ("none", "none", "early")
    expected = {10: "low", 11: "mid", 30: "mid", 31: "high"}
    for week, clicks in enumerate(expected):
        log_activity(con, "s1", week + 1, "quiz", clicks - 1)
        log_activity(con, "s1", week + 1, "glossary", 1)  # every item type counts
    for week, band in enumerate(expected.values()):
        assert live_state(con, "s1", week + 1, cutoffs, cfg).effort_band == band
    # A score known only at week 3 is future data at week 2.
    log_score(con, "s1", 1, 3, cfg.score_low_max - 1)
    assert live_state(con, "s1", 2, cutoffs, cfg).score_band == "none"
    assert live_state(con, "s1", 3, cutoffs, cfg).score_band == "low"


def test_live_points_and_refresh(tmp_path, cfg, cutoffs):
    con = init_db(tmp_path / "live.db")
    fill_students(con, 120, seed=1, prefix="t")
    train = live_points(con, CANDIDATES, cutoffs, cfg)
    assert len(train) == expected_points(con)
    activity = pd.read_sql_query("SELECT * FROM activity WHERE student_id = 't0'", con)
    row = train[(train["student_id"] == "t0") & (train["week"] == 0)].iloc[0]
    used = set(activity.loc[(activity["week"] == 1) & (activity["clicks"] > 0), "item_type"])
    assert {a for a in CANDIDATES if row[f"act_{a}"]} == used
    # Train ids are integers in the real points. Mixed key types must work.
    train = train.assign(course_id="AAA_2014J",
                         student_id=train["student_id"].str[1:].astype(int))

    live_con = init_db(tmp_path / "live2.db")
    fill_students(live_con, 40, seed=2, prefix="L")
    add_student(live_con, "no_outcome", "AAA")
    log_activity(live_con, "no_outcome", 0, "quiz", 5)
    log_activity(live_con, "no_outcome", 1, "quiz", 5)
    live_dir = tmp_path / "live"
    tables = refresh_tables(live_con, train, CANDIDATES, cutoffs, cfg, live_dir)
    assert live_tables_exist("goal_pass", live_dir)
    loaded = load_lift_tables("goal_pass", tmp_path / "no_app", live_dir)
    assert len(loaded[2]) == len(tables["goal_pass"][2])
    quiz = tables["goal_pass"][2].query("action == 'quiz'")
    live = live_points(live_con, CANDIDATES, cutoffs, cfg)
    assert len(live) == expected_points(live_con)  # no point without an outcome
    # Bands where all or none used the activity drop out (SPEC 10), so the count is at most
    # the compared points, and the live points raise it above the train-only count.
    compared = pd.concat([train, live])["next_effort_band"].ne("none").sum()
    train_only = lift_tables(train, CANDIDATES, "goal_pass", cfg)[2].query("action == 'quiz'")
    n_live = quiz[["n_did", "n_did_not"]].sum().sum()
    assert train_only[["n_did", "n_did_not"]].sum().sum() < n_live <= compared


def test_advise_logs_explored(tmp_path, cfg, cutoffs):
    con = init_db(tmp_path / "live.db")
    fill_students(con, 120, seed=1, prefix="t")
    tables = refresh_tables(con, live_points(con, CANDIDATES, cutoffs, cfg).iloc[:0],
                            CANDIDATES, cutoffs, cfg, tmp_path / "live")["goal_pass"]
    rng = np.random.default_rng(cfg.seed)
    for share, flag in ((1.0, 1), (0.0, 0)):
        out = advise(con, "t0", 1, "goal_pass", tables, CANDIDATES, cutoffs,
                     replace(cfg, sim_explore_share=share), rng)
        assert out["explored"] == flag
        logged = con.execute("SELECT explored FROM advice ORDER BY rowid DESC LIMIT 1")
        assert logged.fetchone()[0] == flag
    for _ in range(500):
        advise(con, "t1", 2, "goal_pass", tables, CANDIDATES, cutoffs, cfg, rng)
    (share,) = con.execute("SELECT avg(explored) FROM advice WHERE student_id = 't1'").fetchone()
    assert abs(share - cfg.sim_explore_share) <= 0.05


def test_json_is_strict():
    payload = {"a": np.float64("nan"), "b": np.int64(3), "c": pd.NA, "d": np.bool_(True),
               "e": [float("nan"), 1.5], "f": (np.int32(1),)}
    out = strict_loads(dumps(payload))
    assert out == {"a": None, "b": 3, "c": None, "d": True, "e": [None, 1.5], "f": [1]}


def test_cli_recommend_json(capsys):
    from liftpath.cli import main
    if not (ROOT / "data" / "app" / "effort_cutoffs.parquet").exists():
        pytest.skip("needs make app-data")
    main(["recommend", "--module", "BBB", "--week", "6", "--score-band", "mid",
          "--effort-band", "low", "--goal", "pass", "--json"])
    out = strict_loads(capsys.readouterr().out)
    assert out["status"] in {"recommend", "no_clear_winner", "abstain"}
    assert out["state"]["week_block"] in {"early", "mid", "late"}
