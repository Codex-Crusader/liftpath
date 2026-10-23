"""Teacher view logic: groups, the inactive streak, the rescue flag, preferences and messages."""

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.lift import RECOMMEND
from liftpath.live import load_lift_tables
from liftpath.route import rescue_card
from liftpath.teacher import (
    GO_BACK,
    GROUP_ORDER,
    NEXT_STEP,
    NO_ACTIVITY,
    NO_CHANGE,
    Prefs,
    class_summary,
    class_table,
    clean_prefs,
    default_prefs,
    default_week,
    inactive_weeks,
    load_prefs,
    save_prefs,
)

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "data" / "app"
COURSE = "GGG_2014J"
GOAL = "goal_pass"


@pytest.fixture(scope="module")
def cfg():
    base = load_config(ROOT / "config.yaml")
    meta = APP / "meta.json"
    return replace(base, **json.loads(meta.read_text("utf-8"))["config"]) if meta.exists() else base


@pytest.fixture(scope="module")
def data(cfg, tmp_path_factory):
    if not (APP / "students.parquet").exists():
        pytest.skip("needs make app-data")
    students = pd.read_parquet(APP / "students.parquet")
    recovery = pd.read_parquet(APP / "recovery_points.parquet")
    tables = load_lift_tables(GOAL, APP, tmp_path_factory.mktemp("no_live"))
    week = default_week(students, recovery, COURSE, cfg)
    return students, recovery, tables, week


@pytest.fixture(scope="module")
def table(cfg, data):
    students, recovery, tables, week = data
    return class_table(students, recovery, tables, COURSE, week, GOAL, cfg, default_prefs(cfg))


def test_inactive_weeks_counts_only_past_weeks():
    rows = pd.DataFrame({
        "student_id": [1, 1, 1, 1, 2, 2, 3],
        "week": [0, 1, 2, 3, 2, 3, 3],
        "effort_band": ["low", "none", "none", "high", "none", "none", "none"],
    })
    assert inactive_weeks(rows, 2).to_dict() == {1: 2, 2: 1}
    # Week 3 activity of student 1 is in the future at week 2 and resets the streak at week 3.
    assert inactive_weeks(rows, 3).to_dict() == {1: 0, 2: 2, 3: 1}


def test_groups_follow_the_rules(cfg, table):
    has_back = table["back_action"].notna()
    idle = table["inactive_weeks"] >= cfg.teacher_inactive_weeks
    is_rec = table["status"] == RECOMMEND
    assert (table.loc[has_back, "group"] == GO_BACK).all()
    assert (table.loc[~has_back & idle, "group"] == NO_ACTIVITY).all()
    assert (table.loc[~has_back & ~idle & is_rec, "group"] == NEXT_STEP).all()
    assert (table.loc[~has_back & ~idle & ~is_rec, "group"] == NO_CHANGE).all()
    order = table["group"].map(GROUP_ORDER.index)
    assert order.is_monotonic_increasing
    assert table["student_id"].is_unique


def test_go_back_flag_matches_the_rescue_card(cfg, data, table):
    """The list and the student panel must agree on every student."""
    _, recovery, _, _ = data
    schedule = pd.read_parquet(APP / "plan_schedule.parquet")
    for _, row in table.iterrows():
        card = rescue_card(row, recovery, schedule, cfg)
        assert (card is not None) == (row["group"] == GO_BACK), row["student_id"]
        if card is not None:
            assert card.action == row["back_action"]


def test_differs_means_usual_advice_is_another_activity(table):
    rows = table[table["differs"]]
    assert (rows["status"] == RECOMMEND).all()
    assert (rows["usual_action"] != rows["action"]).all()
    summary = class_summary(table)
    assert summary["n_differ"] == len(rows) <= summary["n_suggested"]
    assert sum(summary["counts"].values()) == len(table)


def test_texts_use_teacher_names_and_no_numbers_by_default(cfg, data, table):
    students, recovery, tables, week = data
    assert not table["suggestion"].str.contains("%").any()
    action = table.loc[table["status"] == RECOMMEND, "action"].iloc[0]
    prefs = replace(default_prefs(cfg), activity_names={action: "Weekly Practice"},
                    show_numbers=True)
    named = class_table(students, recovery, tables, COURSE, week, GOAL, cfg, prefs)
    rows = named[named["action"] == action]
    assert rows["suggestion"].str.contains("Weekly Practice").all()
    assert rows["suggestion"].str.contains("%").all()


def test_a_course_without_suggestions_does_not_fail(cfg, data):
    students, recovery, _, _ = data
    tables = load_lift_tables("goal_distinction", APP, Path("no_live_folder"))
    for course in students["course_id"].unique():
        week = default_week(students, recovery, course, cfg)
        out = class_table(students, recovery, tables, course, week, "goal_distinction", cfg,
                          default_prefs(cfg))
        assert out["suggestion"].map(len).gt(0).all()


@pytest.mark.parametrize("template", ["{x} $suggestion }", "Dear $student, $ $missing",
                                      "No token at all"])
def test_message_template_never_fails(cfg, data, template):
    students, recovery, tables, week = data
    prefs = replace(default_prefs(cfg), message_template=template)
    out = class_table(students, recovery, tables, COURSE, week, GOAL, cfg, prefs)
    assert out["message"].map(len).gt(0).all()


def test_clean_prefs_drops_bad_values(cfg):
    prefs, notes = clean_prefs({"goal": "goal_recover", "inactive_weeks": 0,
                                "show_numbers": "yes", "course": "BBB_2014J",
                                "activity_names": {"quiz": "  Quick check ", "url": "", 3: "x"},
                                "unknown": 1}, cfg)
    assert prefs.goal == default_prefs(cfg).goal
    assert prefs.inactive_weeks == cfg.teacher_inactive_weeks
    assert prefs.show_numbers is False
    assert prefs.course == "BBB_2014J"
    assert prefs.activity_names == {"quiz": "Quick check"}
    assert len(notes) == 3
    assert clean_prefs(["not", "a", "dict"], cfg)[0] == default_prefs(cfg)
    too_many = clean_prefs({"inactive_weeks": cfg.teacher_inactive_weeks_max + 1}, cfg)[0]
    assert too_many.inactive_weeks == cfg.teacher_inactive_weeks


def test_prefs_round_trip_and_bad_file(cfg, tmp_path):
    path = tmp_path / "teacher_settings.json"
    assert load_prefs(path, cfg) == (default_prefs(cfg), [])
    prefs = Prefs(course="CCC_2014J", goal="goal_distinction", inactive_weeks=3,
                  show_numbers=True, activity_names={"quiz": "Quick check"},
                  message_template="Hi $student. $suggestion")
    save_prefs(path, prefs)
    assert load_prefs(path, cfg) == (prefs, [])
    path.write_text("{not json", encoding="utf-8")
    loaded, notes = load_prefs(path, cfg)
    assert loaded == default_prefs(cfg) and notes
