"""Teacher view and Settings tab of the app (Streamlit code). The logic is in teacher.py."""

import html
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from liftpath.config import Config
from liftpath.lift import ABSTAIN, RECOMMEND
from liftpath.recommend import GOAL_TEXT, State, label, recommend
from liftpath.route import PROJECTION_NOTE, plan_route, rescue_card
from liftpath.style import (
    BORDER,
    DARK_BG,
    DARK_SURFACE,
    DARK_SURFACE_2,
    DARK_TEXT,
    DARK_TEXT_SECONDARY,
    STATUS_COLORS,
    STATUS_TINTS,
)
from liftpath.teacher import (
    ADMIN_SETTINGS,
    GO_BACK,
    GROUP_ORDER,
    GROUPS,
    LOCKED_SETTINGS,
    NO_ACTIVITY,
    NO_CHANGE,
    SORT_NOTE,
    TEACHER_GOALS,
    Prefs,
    activity_name,
    class_summary,
    class_table,
    clean_prefs,
    course_label,
    default_course,
    default_prefs,
    default_week,
    load_prefs,
    save_prefs,
    settings_rows,
)

GOAL_NAMES = {"goal_pass": "Pass", "goal_distinction": "Distinction"}
GOAL_WORDS = {"goal_pass": "passed", "goal_distinction": "got a distinction"}
ALL = "all"
LIST_HEIGHT = 560
TILE_TEXT = {
    GO_BACK: "Low mark on the last assessment. Going back helped similar students.",
    NO_ACTIVITY: "No clicks for {weeks} weeks or more.",
    "next_step": "One activity clearly helped similar students.",
    NO_CHANGE: "No activity clearly helps more. Keep the plan.",
}
CSS = f"""
<style>
.lp-tiles {{display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:12px; margin:4px 0 8px 0;}}
.lp-tile {{background:{DARK_SURFACE}; border:1px solid {BORDER}; border-left:6px solid var(--c);
  border-radius:12px; padding:12px 16px;}}
.lp-tile .n {{font-size:2rem; font-weight:700; line-height:1.15; color:{DARK_TEXT};}}
.lp-tile .t {{font-weight:600; color:var(--c);}}
.lp-tile .d {{font-size:0.85rem; color:{DARK_TEXT_SECONDARY}; margin-top:2px;}}
.lp-badge {{display:inline-block; padding:2px 12px; border-radius:999px; font-weight:600;
  font-size:0.85rem; color:var(--c); background:var(--bg); border:1px solid var(--c);}}
.lp-chip {{display:inline-block; padding:3px 11px; border-radius:999px; font-size:0.85rem;
  margin:0 6px 6px 0; background:{DARK_SURFACE_2}; border:1px solid {BORDER}; color:{DARK_TEXT};}}
.lp-name {{font-size:1.35rem; font-weight:700; color:{DARK_TEXT}; margin-right:10px;}}
.lp-steps {{margin:6px 0 4px 0;}}
.lp-step {{display:flex; gap:12px; align-items:flex-start; padding:10px 0;
  border-top:1px solid {BORDER};}}
.lp-step:first-child {{border-top:none;}}
.lp-num {{flex:0 0 28px; height:28px; border-radius:50%; background:var(--c); color:{DARK_BG};
  text-align:center; line-height:28px; font-weight:700; font-size:0.9rem;}}
.lp-step .h {{font-weight:600; color:{DARK_TEXT};}}
.lp-step .s {{font-size:0.9rem; color:{DARK_TEXT_SECONDARY};}}
.lp-hero {{background:{DARK_SURFACE}; border:1px solid {BORDER}; border-radius:14px;
  padding:18px 22px; margin:6px 0 14px 0; display:flex; gap:22px; align-items:center;
  flex-wrap:wrap;}}
.lp-hero .big {{font-size:2.6rem; font-weight:800; line-height:1; white-space:nowrap;
  color:{STATUS_COLORS["next_step"]};}}
.lp-hero .big span {{font-size:1.1rem; font-weight:600; color:{DARK_TEXT_SECONDARY};}}
.lp-hero .txt {{flex:1 1 320px; color:{DARK_TEXT}; font-size:1.02rem;}}
.lp-hero .txt b {{font-weight:700;}}
.lp-hero .sub {{color:{DARK_TEXT_SECONDARY}; font-size:0.88rem; margin-top:4px;}}
.lp-insight {{background:{DARK_SURFACE}; border:1px solid {BORDER}; border-radius:12px;
  padding:10px 16px; color:{DARK_TEXT}; margin-bottom:8px;}}
.lp-plan {{width:100%; border-collapse:collapse; font-size:0.92rem;}}
.lp-plan td {{padding:6px 4px; border-top:1px solid {BORDER}; color:{DARK_TEXT};}}
.lp-plan td.w {{color:{DARK_TEXT_SECONDARY}; width:140px;}}
[data-testid="stCode"] pre, [data-testid="stCode"] code {{font-size:0.98rem;
  font-family:"Source Sans", "Source Sans Pro", sans-serif !important;}}
</style>
"""


@dataclass(frozen=True)
class TeacherContext:
    students: pd.DataFrame
    recovery: pd.DataFrame
    tables_for: Callable[[str], dict[int, pd.DataFrame]]
    plan: tuple | None
    cfg: Config
    settings_file: Path
    candidates: list[str]


def esc(value) -> str:
    return html.escape(str(value))


def badge(group: str) -> str:
    return (f'<span class="lp-badge" style="--c:{STATUS_COLORS[group]};'
            f'--bg:{STATUS_TINTS[group]}">{esc(GROUPS[group])}</span>')


def tiles(summary: dict, prefs: Prefs) -> str:
    parts = []
    for group in GROUP_ORDER:
        text = TILE_TEXT[group].format(weeks=prefs.inactive_weeks)
        parts.append(f'<div class="lp-tile" style="--c:{STATUS_COLORS[group]}">'
                     f'<div class="n">{summary["counts"][group]}</div>'
                     f'<div class="t">{esc(GROUPS[group])}</div>'
                     f'<div class="d">{esc(text)}</div></div>')
    return f'<div class="lp-tiles">{"".join(parts)}</div>'


def hero(summary: dict) -> str:
    """The class-level finding: how often LiftPath differs from the usual advice."""
    n, k = summary["n_suggested"], summary["n_differ"]
    if n == 0:
        return ('<div class="lp-hero"><div class="txt">This week, no activity clearly helped '
                'more for the students in this course. Keep the current plan.</div></div>')
    return (f'<div class="lp-hero"><div class="big">{k}<span> of {n}</span></div>'
            '<div class="txt">students with a suggestion get <b>different advice</b> from '
            'LiftPath than from the usual rule, "do what similar students did".'
            '<div class="sub">The usual rule copies the activity that similar students used '
            'most. LiftPath suggests the activity that helped similar students who studied '
            'about as much.</div></div></div>')


def usual_text(row: pd.Series) -> str | None:
    """One plain sentence about the usual advice, or None if it agrees or is missing."""
    if not row["differs"]:
        return None
    lead = f"Similar students used the {row['usual_name']} most."
    if pd.isna(row["usual_lift"]):
        return f"{lead} Too few students to tell if it helped."
    if row["usual_ci_low"] <= 0 <= row["usual_ci_high"]:
        return f"{lead} With the same effort, it did not clearly help."
    if row["usual_lift"] < 0:
        return f"{lead} With the same effort, students who used it did worse."
    return f"{lead} With the same effort, it helped less."


def step_html(number: int, group: str, head: str, sub: str) -> str:
    return (f'<div class="lp-step"><div class="lp-num" style="--c:{STATUS_COLORS[group]}">'
            f'{number}</div><div><div class="h">{esc(head)}</div>'
            f'<div class="s">{esc(sub)}</div></div></div>')


def suggestion_steps(row: pd.Series, goal: str, prefs: Prefs) -> str:
    """The numbered "what to suggest" steps, with the plain reason under each."""
    steps = []
    if row["inactive_weeks"] >= prefs.inactive_weeks:
        steps.append((NO_ACTIVITY, "Contact the student",
                      f"No clicks in the course for {row['inactive_weeks']} weeks."))
    if pd.notna(row["back_action"]):
        name = activity_name(row["back_action"], prefs)
        steps.append((GO_BACK, f"Go back to the earlier {name}",
                      f"Before the next assessment. After a low mark, "
                      f"{row['back_p1_avg']:.0%} of similar students who did this passed the "
                      f"next assessment. Of those who did not, {row['back_p0_avg']:.0%} "
                      "passed."))
    if row["status"] == RECOMMEND:
        name = activity_name(row["action"], prefs)
        text = (f"Of similar students who did this next week, {row['p1_avg']:.0%} "
                f"{GOAL_WORDS[goal]}. Of those who did not, {row['p0_avg']:.0%} did. Both "
                "groups studied about as much.")
        usual = usual_text(row)
        steps.append(("next_step", f"Next week: the {name}",
                      f"{text} {usual}" if usual else text))
    elif not steps or row["status"] == ABSTAIN:
        text = ("Too few similar past students to compare." if row["status"] == ABSTAIN
                else "No activity clearly helps more for students in this position.")
        steps.append((NO_CHANGE, "Keep the current plan", text))
    return ('<div class="lp-steps">'
            + "".join(step_html(i, g, h, s) for i, (g, h, s) in enumerate(steps, start=1))
            + "</div>")


def plan_html(route, prefs: Prefs) -> str:
    """One row per run of equal steps. A step decided at week w is for week w + 1."""
    steps = pd.DataFrame({
        "week": [s.week + 1 for s in route.steps],
        "what": [f"The {activity_name(s.action, prefs)}" if s.status == RECOMMEND
                 else "Keep the current plan" for s in route.steps]})
    run = steps["what"].ne(steps["what"].shift()).cumsum()
    runs = steps.groupby(run).agg(first=("week", "min"), last=("week", "max"),
                                  what=("what", "first"))
    weeks = np.where(runs["first"] == runs["last"], "Week " + runs["first"].astype(str),
                     "Weeks " + runs["first"].astype(str) + " to " + runs["last"].astype(str))
    rows = [f'<tr><td class="w">{esc(w)}</td><td>{esc(t)}</td></tr>'
            for w, t in zip(weeks, runs["what"], strict=True)]
    return f'<table class="lp-plan">{"".join(rows)}</table>'


def chips(row: pd.Series) -> str:
    items = [row["mark"]]
    items.append(f"No clicks for {row['inactive_weeks']} weeks" if row["inactive_weeks"] > 1
                 else row["activity"])
    if pd.notna(row["back_score"]):
        items.append(f"Last assessment: {row['back_score']:.0f}")
    return "".join(f'<span class="lp-chip">{esc(i)}</span>' for i in items)


def context_bar(ctx: TeacherContext, prefs: Prefs) -> tuple[str, int, str]:
    courses = sorted(ctx.students["course_id"].unique())
    start_course = (prefs.course if prefs.course in courses
                    else default_course(ctx.students, prefs.goal))
    first = courses.index(start_course)
    c1, c2, c3 = st.columns([2, 2, 3], vertical_alignment="bottom")
    course = c1.selectbox("Course", courses, index=first, format_func=course_label,
                          key="teacher_course")
    weeks = sorted(ctx.students.loc[ctx.students["course_id"] == course, "week"].unique())
    start = default_week(ctx.students, ctx.recovery, course, ctx.cfg)
    week = c2.selectbox("Week of the course", weeks, index=weeks.index(start),
                        format_func=lambda w: f"Week {w}", key=f"teacher_week_{course}")
    goal = c3.segmented_control("Goal", TEACHER_GOALS, default=prefs.goal,
                                format_func=GOAL_NAMES.get, key="teacher_goal")
    return course, int(week), goal or prefs.goal


def pick_from_list(shown: pd.DataFrame) -> None:
    """A click on a list row opens that student, once per new click."""
    event = st.dataframe(
        pd.DataFrame({"Student": shown["student_id"].astype(str),
                      "Status": shown["group_label"], "LiftPath suggests": shown["short"],
                      "Similar students mostly did": shown["usual_name"].where(
                          shown["status"] == RECOMMEND, "")}),
        hide_index=True, width="stretch", height=LIST_HEIGHT, on_select="rerun",
        selection_mode="single-row", key="teacher_list",
        column_config={"Student": st.column_config.TextColumn(width="small"),
                       "Status": st.column_config.TextColumn(width="small"),
                       "LiftPath suggests": st.column_config.TextColumn(width="medium"),
                       "Similar students mostly did": st.column_config.TextColumn(
                           width="medium")})
    rows = list(event.selection.rows) if event and event.selection else []
    if rows and rows != st.session_state.get("teacher_list_applied") and rows[0] < len(shown):
        st.session_state["teacher_student"] = int(shown.iloc[rows[0]]["student_id"])
    st.session_state["teacher_list_applied"] = rows


def evidence(ctx: TeacherContext, row: pd.Series, goal: str) -> None:
    with st.expander("Show the evidence", icon=":material/fact_check:"):
        if pd.notna(row["back_action"]) and ctx.plan is not None:
            card = rescue_card(row, ctx.recovery, ctx.plan[1], ctx.cfg)
            if card is not None:
                st.markdown("**Go back first**")
                st.write(card.rationale)
        state = State(row["module"], row["week_block"], row["score_band"], row["effort_band"])
        rec = recommend(state, goal, ctx.tables_for(goal), ctx.cfg)
        st.markdown("**Next week**")
        st.write(rec.rationale)
        st.caption("LiftPath compares students in the same situation who studied about as much "
                   "in the same week. A count below "
                   f"{ctx.cfg.display_min_count} shows as 'fewer than "
                   f"{ctx.cfg.display_min_count}'. The data is observational: it is evidence, "
                   "not proof of cause. The 'Your route' tab has the full table for each "
                   "activity.")


def detail_panel(ctx: TeacherContext, table: pd.DataFrame, shown: pd.DataFrame, goal: str,
                 prefs: Prefs) -> None:
    ids = shown["student_id"].tolist()
    if not ids:
        st.info("No students in this group this week.")
        return
    if st.session_state.get("teacher_student") not in ids:
        st.session_state["teacher_student"] = ids[0]
    groups = table.set_index("student_id")["group_label"]
    student = st.selectbox("Open a student", ids, key="teacher_student",
                           format_func=lambda i: f"{i}  ·  {groups[i]}")
    row = table[table["student_id"] == student].iloc[0]
    with st.container(border=True):
        st.markdown(f'<span class="lp-name">Student {esc(student)}</span>{badge(row["group"])}',
                    unsafe_allow_html=True)
        st.markdown(chips(row), unsafe_allow_html=True)
        st.markdown("##### What to suggest")
        st.markdown(suggestion_steps(row, goal, prefs), unsafe_allow_html=True)
        if ctx.plan is not None:
            projector, schedule = ctx.plan
            with st.spinner("Planning the next weeks..."):
                route = plan_route(row, goal, ctx.tables_for(goal), projector, schedule,
                                   ctx.cfg)
            planned = [s for s in route.steps if s.status == RECOMMEND]
            if route.steps:
                st.markdown(f"##### Plan for the next {len(route.steps)} weeks")
            if route.steps and not planned:
                st.write("No change suggested for these weeks. Keep the current plan.")
            elif route.steps:
                st.markdown(plan_html(route, prefs), unsafe_allow_html=True)
                if not np.isnan(route.projected_route):
                    plan, typical = (f"{route.projected_route:.0%}",
                                     f"{route.projected_typical:.0%}")
                    compare = ("about the same as on the typical path" if plan == typical
                               else f"against {typical} on the typical path")
                    st.caption(f"Projected chance of {GOAL_TEXT[goal]} with this plan: {plan}, "
                               f"{compare}. {PROJECTION_NOTE}")
        st.markdown("##### Message for the student")
        st.code(row["message"], language=None, wrap_lines=True)
        st.caption("Copy it with the icon at the top right of the box. Change the text in "
                   "Settings.")
    evidence(ctx, row, goal)


def teacher_tab(ctx: TeacherContext) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    prefs, notes = load_prefs(ctx.settings_file, ctx.cfg)
    for note in notes:
        st.warning(note)
    course, week, goal = context_bar(ctx, prefs)
    with st.spinner("Finding the next step for each student..."):
        table = class_table(ctx.students, ctx.recovery, ctx.tables_for(goal), course, week,
                            goal, ctx.cfg, prefs)
    summary = class_summary(table)
    st.markdown(hero(summary), unsafe_allow_html=True)
    st.markdown(tiles(summary, prefs), unsafe_allow_html=True)

    counts = summary["counts"]
    choice = st.segmented_control(
        "Show", [ALL, *GROUP_ORDER], default=ALL, key="teacher_filter",
        format_func=lambda g: (f"All students ({len(table)})" if g == ALL
                               else f"{GROUPS[g]} ({counts[g]})"))
    shown = table if choice in (None, ALL) else table[table["group"] == choice]

    left, right = st.columns([5, 4], gap="large")
    with left:
        pick_from_list(shown)
        st.caption(SORT_NOTE)
        export = shown[["student_id", "group_label", "mark", "activity", "inactive_weeks",
                        "suggestion", "message"]].rename(columns={"group_label": "status"})
        st.download_button("Download this list (CSV)", export.to_csv(index=False),
                           file_name=f"liftpath_{course}_week{week}.csv", mime="text/csv",
                           icon=":material/download:", key="teacher_download")
    with right:
        detail_panel(ctx, table, shown, goal, prefs)


def save_settings(ctx: TeacherContext, values: dict) -> list[str]:
    prefs, notes = clean_prefs(values, ctx.cfg)
    save_prefs(ctx.settings_file, prefs)
    return notes


def settings_tab(ctx: TeacherContext) -> None:
    prefs, notes = load_prefs(ctx.settings_file, ctx.cfg)
    for note in notes:
        st.warning(note)
    done = st.session_state.pop("settings_done", None)
    if done is not None:
        for note in done[1]:
            st.warning(note)
        st.success(done[0], icon=":material/check:")
    st.subheader("Your preferences")
    st.caption("These settings change only what the teacher view shows. They do not change how "
               "LiftPath finds a suggestion.")
    courses = sorted(ctx.students["course_id"].unique())
    with st.form("teacher_settings", border=True):
        c1, c2 = st.columns(2)
        first = (prefs.course if prefs.course in courses
                 else default_course(ctx.students, prefs.goal))
        course = c1.selectbox("Course to open first", courses, index=courses.index(first),
                              format_func=course_label, key="set_course")
        goal = c2.radio("Goal to open first", TEACHER_GOALS,
                        index=TEACHER_GOALS.index(prefs.goal), format_func=GOAL_NAMES.get,
                        horizontal=True, key="set_goal")
        weeks = c1.number_input("Mark a student 'No recent activity' after this many weeks "
                                "without clicks", min_value=1,
                                max_value=ctx.cfg.teacher_inactive_weeks_max,
                                value=prefs.inactive_weeks, key="set_inactive")
        numbers = c2.toggle("Add percentages to the suggestions in the list and the download",
                            value=prefs.show_numbers, key="set_numbers")
        st.markdown("**Activity names**")
        st.caption("Write the names that your students see in your course. Leave a cell empty "
                   "to keep the LiftPath name.")
        names = st.data_editor(
            pd.DataFrame({"activity": ctx.candidates,
                          "LiftPath name": [label(a) for a in ctx.candidates],
                          "your name": [prefs.activity_names.get(a, "")
                                        for a in ctx.candidates]}),
            disabled=["activity", "LiftPath name"], hide_index=True, width="stretch",
            key="set_names")
        template = st.text_area(
            "Message to the student", value=prefs.message_template, height=200,
            key="set_template",
            help="$suggestion is replaced with the suggestion for the student. $student is "
                 "replaced with the student ID.")
        saved = st.form_submit_button("Save settings", type="primary", icon=":material/save:")
    if saved:
        your = names["your name"].fillna("").astype(str).str.strip()
        notes = save_settings(ctx, {
            "course": course, "goal": goal, "inactive_weeks": int(weeks),
            "show_numbers": bool(numbers), "message_template": template,
            "activity_names": dict(zip(names["activity"], your, strict=True))})
        # Run the page again, so the teacher view above uses the new settings at once.
        st.session_state["settings_done"] = ("Saved. The teacher view now uses these "
                                             "settings.", notes)
        st.rerun()
    if st.button("Reset to the defaults", icon=":material/restart_alt:", key="set_reset"):
        save_prefs(ctx.settings_file, default_prefs(ctx.cfg))
        st.session_state["settings_done"] = ("The defaults are back.", [])
        st.rerun()
    st.caption(f"Saved in {ctx.settings_file}. Everyone who uses this app on the same computer "
               "or server shares this file. Separate settings per teacher need a login, and "
               "this version has no login.")

    st.subheader("Course rules")
    st.caption("The administrator sets these in config.yaml. Most changes need a rebuild of the "
               "app data (make all). The steps are in docs/admin_guide.md.")
    st.table(settings_rows(ctx.cfg, ADMIN_SETTINGS).set_index("setting"))

    st.subheader("Fixed rules")
    st.caption("These rules keep the results valid and the student data private. The app does "
               "not let anyone change them.")
    st.table(settings_rows(ctx.cfg, LOCKED_SETTINGS).set_index("setting"))

    st.subheader("Data")
    n_students = ctx.students[["course_id", "student_id"]].drop_duplicates().shape[0]
    st.write(f"This app shows {n_students:,} students in {len(courses)} courses from the Open "
             "University Learning Analytics Dataset (OULAD, 2014J presentations). To use your "
             "own course data, follow docs/admin_guide.md.")
