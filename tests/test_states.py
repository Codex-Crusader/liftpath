from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.schema import write_frames
from liftpath.states import (
    build_decision_points,
    check_variety,
    register_canonical,
    select_candidates,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
TYPES = ["oucontent", "quiz", "forumng", "homepage"]
CANDIDATES = ["oucontent", "quiz", "forumng"]
STATE_COLS = ["week_block", "score_band", "effort_band", "clicks_week",
              *[f"cum_share_{a}" for a in CANDIDATES]]


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    return load_config(CONFIG_PATH)


def courses_frame(rows):
    df = pd.DataFrame(rows, columns=["module", "presentation", "length_days"])
    df.insert(0, "course_id", df["module"] + "_" + df["presentation"])
    return df


def items_frame(courses):
    return pd.DataFrame([
        {"course_id": c, "item_id": i + 1, "item_type": t, "week_from": None, "week_to": None}
        for c in courses["course_id"] for i, t in enumerate(TYPES)
    ])


def enrollments_frame(rows):
    df = pd.DataFrame(rows, columns=["course_id", "student_id", "reg_day", "unreg_day",
                                     "final_result"])
    df["module"] = df["course_id"].str.split("_").str[0]
    df["presentation"] = df["course_id"].str.split("_").str[1]
    for col in ["gender", "age_band", "imd_band", "disability", "region", "highest_education"]:
        df[col] = "x"
    return df


def build(con_folder: Path, frames: dict, cfg, candidates=CANDIDATES) -> pd.DataFrame:
    write_frames(frames, con_folder)
    con = duckdb.connect()
    register_canonical(con, con_folder)
    return build_decision_points(con, cfg, candidates)


def hand_frames():
    courses = courses_frame([("AAA", "2013J", 70), ("AAA", "2014J", 70), ("BBB", "2013J", 70)])
    enrollments = enrollments_frame([
        ("AAA_2013J", 1, -20, None, "Pass"),
        ("AAA_2013J", 2, -20, None, "Fail"),
        ("AAA_2013J", 3, -20, None, "Distinction"),
        ("AAA_2013J", 4, -20, None, "Pass"),
        ("AAA_2013J", 5, -20, 23, "Withdrawn"),
        ("AAA_2013J", 6, 10, None, "Pass"),
        ("AAA_2014J", 7, -20, None, "Pass"),
        ("BBB_2013J", 8, -20, None, "Pass"),
    ])
    # item ids: 1 oucontent, 2 quiz, 3 forumng, 4 homepage
    events = pd.DataFrame([
        ("AAA_2013J", 1, 2, -5, 4),
        ("AAA_2013J", 1, 1, 2, 1),
        ("AAA_2013J", 1, 2, 8, 2),
        ("AAA_2013J", 2, 3, 3, 5),
        ("AAA_2013J", 3, 1, 4, 10),
    ], columns=["course_id", "student_id", "item_id", "day", "clicks"])
    assessments = pd.DataFrame([
        ("AAA_2013J", 10, "TMA", 10, 50.0),
        ("AAA_2013J", 11, "Exam", 70, 100.0),
    ], columns=["course_id", "assessment_id", "kind", "due_day", "weight"])
    submissions = pd.DataFrame([
        ("AAA_2013J", 1, 10, 3, 30.0, False),
        ("AAA_2013J", 2, 10, 12, 50.0, False),
        ("AAA_2013J", 3, 10, 9, 80.0, False),
        ("AAA_2013J", 1, 11, 5, 10.0, False),
    ], columns=["course_id", "student_id", "assessment_id", "submit_day", "score", "banked"])
    return {"courses": courses, "enrollments": enrollments, "items": items_frame(courses),
            "events": events, "assessments": assessments, "submissions": submissions}


@pytest.fixture
def hand_points(tmp_path, cfg):
    return build(tmp_path / "canonical", hand_frames(), cfg).set_index(["student_id", "week"])


def test_effort_bands(hand_points):
    p = hand_points
    assert [p.loc[(s, 0), "effort_band"] for s in (1, 2, 3, 4)] == ["low", "mid", "high", "none"]
    assert p.loc[(1, 0), "next_effort_band"] == "high"
    assert p.loc[(1, 0), "clicks_week"] == 1
    assert p.loc[(1, 0), "clicks_next"] == 2
    assert p.loc[(2, 0), "next_effort_band"] == "none"


def test_score_bands_use_known_day_and_skip_exams(hand_points):
    p = hand_points
    assert [p.loc[(s, 0), "score_band"] for s in (1, 2, 3, 4)] == ["none"] * 4
    assert [p.loc[(s, 1), "score_band"] for s in (1, 2, 3, 4)] == ["low", "mid", "high", "none"]


def test_cum_shares_count_days_before_zero(hand_points):
    p = hand_points
    assert p.loc[(1, 0), "cum_share_quiz"] == pytest.approx(0.8)
    assert p.loc[(1, 0), "cum_share_oucontent"] == pytest.approx(0.2)
    assert p.loc[(1, 1), "cum_share_quiz"] == pytest.approx(6 / 7)
    assert p.loc[(4, 0), "cum_share_quiz"] == 0.0
    assert bool(p.loc[(1, 0), "act_quiz"]) is True
    assert bool(p.loc[(1, 0), "act_oucontent"]) is False


def test_week_block_split_and_goals(hand_points):
    p = hand_points
    assert [p.loc[(1, w), "week_block"] for w in (3, 4, 6, 7)] == ["early", "mid", "mid", "late"]
    assert p.xs(1, level="student_id").index.max() == 8
    assert p.loc[(7, 0), "split"] == "test"
    assert p.loc[(8, 0), "split"] == "train"
    assert p.loc[(1, 0), "split"] == "train"
    assert bool(p.loc[(3, 0), "goal_distinction"]) and bool(p.loc[(3, 0), "goal_pass"])
    assert not p.loc[(5, 0), "goal_pass"]


def test_registration_filter(hand_points):
    weeks_withdrawn = hand_points.xs(5, level="student_id").index
    assert list(weeks_withdrawn) == [0, 1, 2]
    weeks_late = hand_points.xs(6, level="student_id").index
    assert weeks_late.min() == 1


def test_select_candidates_excludes_homepage(tmp_path, cfg):
    frames = hand_frames()
    frames["events"] = pd.concat([frames["events"], pd.DataFrame(
        [("AAA_2013J", 4, 4, 1, 100)], columns=frames["events"].columns)])
    write_frames(frames, tmp_path)
    con = duckdb.connect()
    register_canonical(con, tmp_path)
    assert select_candidates(con, cfg) == ["oucontent", "quiz", "forumng"]
    assert select_candidates(con, replace(cfg, use_fallback_groups=True)) == [
        "reading", "practice", "discussion"]


def random_frames(seed: int, n_students: int = 40, length: int = 70) -> dict:
    rng = np.random.default_rng(seed)
    courses = courses_frame([("AAA", "2013J", length), ("AAA", "2014J", length)])
    rows = []
    for course in courses["course_id"]:
        for s in range(n_students):
            unreg = int(rng.integers(5, length)) if rng.random() < 0.2 else None
            rows.append((course, s, int(rng.integers(-30, 15)), unreg,
                         rng.choice(["Pass", "Fail", "Distinction", "Withdrawn"])))
    enrollments = enrollments_frame(rows)
    days = np.arange(-10, length)
    grid = enrollments[["course_id", "student_id"]].merge(pd.DataFrame({"day": days}),
                                                          how="cross")
    events = grid[rng.random(len(grid)) < 0.3].copy()
    events["item_id"] = rng.integers(1, len(TYPES) + 1, len(events))
    events["clicks"] = rng.integers(1, 6, len(events))
    due = [20, 41, 62]
    assessments = pd.DataFrame(
        [(c, 100 + k, "TMA", d, 30.0) for c in courses["course_id"] for k, d in enumerate(due)]
        + [(c, 199, "Exam", length, 100.0) for c in courses["course_id"]],
        columns=["course_id", "assessment_id", "kind", "due_day", "weight"])
    subs = enrollments[["course_id", "student_id"]].merge(assessments, on="course_id")
    subs["submit_day"] = subs["due_day"] - rng.integers(-3, 10, len(subs))
    subs["score"] = rng.integers(0, 101, len(subs)).astype(float)
    subs["banked"] = False
    return {"courses": courses, "enrollments": enrollments, "items": items_frame(courses),
            "events": events, "assessments": assessments, "submissions": subs}


def test_no_future_data(tmp_path, cfg):
    frames = random_frames(seed=7)
    before = build(tmp_path / "before", frames, cfg)
    cut_week = 4
    last_day = 7 * cut_week + 6
    cut = dict(frames)
    cut["events"] = frames["events"][frames["events"]["day"] <= last_day]
    cut["submissions"] = frames["submissions"][frames["submissions"]["submit_day"] <= last_day]
    after = build(tmp_path / "after", cut, cfg)

    key = ["course_id", "student_id", "week"]
    old = before[before["week"] < cut_week].set_index(key).sort_index()[STATE_COLS]
    new = after[after["week"] < cut_week].set_index(key).sort_index()[STATE_COLS]
    assert len(old) > 0
    pd.testing.assert_frame_equal(old, new)
    later = before[before["week"] >= cut_week].set_index(key)[STATE_COLS]
    assert not later.equals(after[after["week"] >= cut_week].set_index(key)[STATE_COLS])


def test_check_variety_counts_supported_cells(tmp_path, cfg):
    points = build(tmp_path / "canonical", random_frames(seed=3, n_students=200), cfg)
    variety = check_variety(points, CANDIDATES, replace(cfg, min_count=1))
    assert set(variety["candidate"]) == set(CANDIDATES)
    assert variety["share"].between(0, 1).all()
    strict = check_variety(points, CANDIDATES, replace(cfg, min_count=10**6))
    assert (strict["share"] == 0).all()
