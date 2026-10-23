from pathlib import Path

import duckdb
import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.recover import build_recovery_points, recovery_tables
from liftpath.schema import write_frames
from liftpath.states import register_canonical

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CANDIDATES = ["quiz", "oucontent", "resource", "forumng"]


def frames():
    course = "AAA_2013J"
    courses = pd.DataFrame([(course, "AAA", "2013J", 70), ("AAA_2014J", "AAA", "2014J", 70)],
                           columns=["course_id", "module", "presentation", "length_days"])
    enrollments = pd.DataFrame({
        "course_id": course, "module": "AAA", "presentation": "2013J",
        "student_id": [1, 2, 3, 4], "reg_day": -10, "unreg_day": None,
        "final_result": "Pass", "gender": "x", "age_band": "x", "imd_band": "x",
        "disability": "x", "region": "x", "highest_education": "x",
    })
    # Active days: quiz 7 (week_from 1), oucontent median 10, resource 35 (week_from 5),
    # forumng median 40. Old material for the TMA due on day 20: quiz and oucontent.
    items = pd.DataFrame([
        (course, 1, "quiz", 1, 1), (course, 2, "oucontent", None, None),
        (course, 3, "resource", 5, 5), (course, 4, "forumng", None, None),
    ], columns=["course_id", "item_id", "item_type", "week_from", "week_to"])
    events = pd.DataFrame([
        (course, 1, 1, 25, 2),   # old quiz, in the window
        (course, 1, 3, 30, 4),   # resource, not old
        (course, 1, 2, 21, 1),   # old oucontent, in the window
        (course, 3, 2, 10, 5),   # sets the oucontent median to day 10
        (course, 2, 4, 45, 3),   # forumng, not old
        (course, 3, 4, 40, 3),   # sets the forumng median to day 40
        (course, 2, 1, 20, 6),   # on the due day: outside the window
        (course, 2, 1, 51, 6),   # after the next due day: outside the window
    ], columns=["course_id", "student_id", "item_id", "day", "clicks"])
    assessments = pd.DataFrame([
        (course, 10, "TMA", 20, 30.0), (course, 11, "TMA", 50, 30.0),
        (course, 12, "Exam", 70, 100.0),
    ], columns=["course_id", "assessment_id", "kind", "due_day", "weight"])
    submissions = pd.DataFrame([
        (course, 1, 10, 19, 30.0), (course, 1, 11, 49, 45.0),
        (course, 2, 10, 18, 10.0), (course, 2, 11, 50, 30.0),
        (course, 3, 10, 18, 70.0),
        (course, 4, 10, 18, 50.0), (course, 4, 11, 48, 35.0),
    ], columns=["course_id", "student_id", "assessment_id", "submit_day", "score"])
    submissions["banked"] = False
    return {"courses": courses, "enrollments": enrollments, "items": items, "events": events,
            "assessments": assessments, "submissions": submissions}


@pytest.fixture
def points(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    cfg = load_config(CONFIG_PATH)
    write_frames(frames(), tmp_path)
    con = duckdb.connect()
    register_canonical(con, tmp_path)
    return cfg, build_recovery_points(con, cfg, CANDIDATES).set_index("student_id")


def test_triggers(points):
    _, p = points
    # 1 and 2 scored below 40 on the first TMA. 3 scored 70. 4 scored 35 on the last TMA,
    # and the next assessment is an Exam, so there is no k + 1.
    assert sorted(p.index) == [1, 2]
    assert p.loc[1, "low_band"] == "low"
    assert p.loc[2, "low_band"] == "very_low"
    assert (p.loc[1, "due_day"], p.loc[1, "next_due_day"]) == (20, 50)


def test_window_and_old_material(points):
    _, p = points
    assert bool(p.loc[1, "rev_quiz"]) and bool(p.loc[1, "rev_oucontent"])
    assert not p.loc[1, "rev_resource"]
    assert p.loc[1, "window_clicks"] == 7
    assert not p.loc[2, "rev_quiz"]
    assert not p.loc[2, "rev_forumng"]
    assert p.loc[2, "window_clicks"] == 3


def test_goal(points):
    _, p = points
    assert bool(p.loc[1, "goal_recover"])
    assert not p.loc[2, "goal_recover"]


def test_recovery_tables_levels(points):
    cfg, p = points
    tables = recovery_tables(p.reset_index(), CANDIDATES, cfg)
    assert set(tables) == {0, 1}
    assert "module" in tables[0].columns and "module" not in tables[1].columns


def test_points_sorted_by_key(points):
    # The rescue shuffle permutes by row position, so the row order must be fixed.
    _, p = points
    keys = p.reset_index()[["course_id", "student_id", "assessment_id"]]
    assert keys.equals(keys.sort_values(list(keys.columns), ignore_index=True))
