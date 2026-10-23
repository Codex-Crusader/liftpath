"""LiftPath app (BUILD2 Phase F). Reads the files that `make app-data` writes (APP_DATA_DIR,
default data/app). Live mode writes to LIVE_DATA_DIR (default data/live)."""

import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from liftpath.app_charts import (
    WORLD_NAMES,
    projection_chart,
    sim_estimates_chart,
    sim_pass_rate_chart,
)
from liftpath.config import load_config
from liftpath.engine import app_plan
from liftpath.fairness import SMALL_SAMPLE_STUDENTS
from liftpath.figures import POLICY_NAMES
from liftpath.lift import ABSTAIN, LEVELS, NO_CLEAR_WINNER, RECOMMEND
from liftpath.live import (
    CUTOFF_FILE,
    EXPLORE,
    add_student,
    advise,
    init_db,
    live_dir,
    load_lift_tables,
    log_activity,
    log_score,
    refresh_tables,
    reset_live,
    set_outcome,
)
from liftpath.recommend import State, label, situation
from liftpath.rescue import SOLID, build_graph, keystone, rescue_figure, rescue_note
from liftpath.route import ITEM_NOTE, KEEP_LABEL, PROJECTION_NOTE, plan_route, rescue_card
from liftpath.sim import POLICIES
from liftpath.style import BLUE, GRID, MUTED
from liftpath.teacher import prefs_path
from liftpath.teacher_ui import TeacherContext, settings_tab, teacher_tab
from liftpath.trap import trap_lines

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = os.environ.get("APP_DATA_DIR", str(ROOT / "data" / "app"))
HEADLINE_FILE = ROOT / "reports" / "headline.json"
GOAL_NAMES = {"goal_pass": "Pass", "goal_distinction": "Distinction"}
COUNT_COLS = ["n_did", "n_did_not"]
HOLLOW = "rgba(0,0,0,0)"
EFFORT_ORDER = {"low": 0, "mid": 1, "high": 2}
EFFORT_CHOICES = {"same": "Same as now", "low": "Low", "mid": "Mid", "high": "High"}
FINAL_RESULTS = ("Pass", "Distinction", "Fail", "Withdrawn")
PITCH = "Not what students like you did. What helped students like you."
DEMO_BANNER = ("Demo mode. Data resets on restart. The simulator shows how the loop learns "
               "at scale.")
TABS = ["Teacher view", "Your route", "Simulator", "Try it", "Rescue map", "Evidence",
        "Settings"]


@st.cache_data
def load_json(folder: str, name: str) -> dict | None:
    path = Path(folder) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@st.cache_data
def load_table(folder: str, name: str) -> pd.DataFrame | None:
    path = Path(folder) / name
    if not path.exists():
        return None
    table = pd.read_parquet(path)
    # Suppressed counts are NULL. Floats keep the comparisons in the recommendation rule safe.
    for col in [c for c in COUNT_COLS if c in table]:
        table[col] = table[col].astype(float)
    return table


@st.cache_data
def cached_lift_tables(goal: str, app_dir: str, live_folder: str) -> dict[int, pd.DataFrame]:
    """The live tables when they exist (BUILD2 Phase D), else the app tables. The folders
    are part of the cache key."""
    return load_lift_tables(goal, Path(app_dir), Path(live_folder))


def lift_tables(goal: str) -> dict[int, pd.DataFrame]:
    return cached_lift_tables(goal, APP_DIR, str(live_dir()))


@st.cache_resource
def plan_data(app_dir: str):
    """The route lookups and the item schedule, or None if the app data has no plan files."""
    try:
        return app_plan(Path(app_dir))
    except ValueError:
        return None


@st.cache_resource
def live_store(db_path: str):
    """One demo database per server process. It starts empty: data resets on restart."""
    path = Path(db_path)
    reset_live(path.parent, path.name)
    cached_lift_tables.clear()
    return init_db(path)


def app_config(meta: dict):
    return replace(load_config(ROOT / "config.yaml"), **meta["config"])


def count_text(value, cfg) -> str:
    return (f"fewer than {cfg.display_min_count}" if pd.isna(value)
            else f"{int(value):,}")


def pct(value) -> str:
    """A difference of two rates, in percentage points."""
    return "" if value is None or pd.isna(value) else f"{100 * value:+.1f} pp"


def headline(status: str, action) -> str:
    if status == RECOMMEND:
        return f"Next step: {label(action)}"
    if status == EXPLORE:
        return f"Explore: try {label(action)}"
    if status == NO_CLEAR_WINNER:
        return "No clear winner"
    return "Not enough data"


def lift_chart(rows: pd.DataFrame, highlight, title: str, names=label) -> go.Figure:
    """Horizontal bars with 95% range whiskers, in percentage points."""
    rows = rows.sort_values("lift")
    lift, low, high = (100 * rows[c] for c in ("lift", "ci_low", "ci_high"))
    colors = [BLUE if a == highlight else MUTED for a in rows["action"]]
    fig = go.Figure(go.Bar(
        x=lift, y=[names(a) for a in rows["action"]], orientation="h",
        marker_color=colors,
        error_x={"type": "data", "array": high - lift, "arrayminus": lift - low,
                 "color": "#52514e", "thickness": 1.5},
        hovertemplate="%{y}: %{x:+.1f} pp<extra></extra>"))
    fig.update_layout(title=title, xaxis_tickformat="+.1f", xaxis_ticksuffix=" pp",
                      template="simple_white",
                      height=80 + 36 * len(rows), margin={"l": 10, "r": 10, "t": 50, "b": 30})
    fig.update_xaxes(gridcolor=GRID, showgrid=True, zeroline=True, zerolinecolor=MUTED)
    return fig


def candidate_rows(goal: str, state: State, level: int) -> pd.DataFrame:
    table = lift_tables(goal)[level]
    values = {"module": state.module, "week_block": state.week_block,
              "score_band": state.score_band, "effort_band": state.effort_band}
    mask = pd.Series(True, index=table.index)
    for col in LEVELS[level]:
        mask &= table[col] == values[col]
    return table[mask]


def header() -> None:
    st.title("LiftPath")
    st.caption(PITCH)


def headline_metrics() -> None:
    """The judge metrics. They open the Evidence tab, so the teacher view stays simple."""
    if HEADLINE_FILE.exists():
        metrics = json.loads(HEADLINE_FILE.read_text(encoding="utf-8")).get("metrics", [])
        items = [(m["label"], m["value"], m.get("help")) for m in metrics]
    else:
        results = load_json(APP_DIR, "eval_results.json")
        if results is None:
            return
        data = results["goals"]["goal_pass"]
        lp = pd.DataFrame(data["results"]).set_index("name").loc["liftpath"]
        items = [
            ("LiftPath net lift (pass)", pct(lp["net_lift"]),
             f"95% range {pct(lp['net_ci_low'])} to {pct(lp['net_ci_high'])}. Test students."),
            ("Recommend share", f"{lp['coverage']:.0%}",
             "Share of test student-weeks with a clear recommendation."),
        ]
        if "disagreement" in data:
            items.append(("Differs from 'similar students' advice",
                          f"{data['disagreement']['user_cf']:.0%}",
                          "Share of common test points where LiftPath and user_cf differ."))
    for col, (name, value, help_text) in zip(st.columns(len(items)), items, strict=True):
        col.metric(name, value, help=help_text)


def pick_student(students: pd.DataFrame, goal: str) -> pd.Series:
    c1, c2, c3 = st.columns(3)
    module = c1.selectbox("Module", sorted(students["module"].unique()), key="route_module")
    in_module = students[students["module"] == module]
    # Students with the most level 0 recommendations come first, so the demo opens on a card
    # with the most specific evidence.
    is_rec = in_module[f"{goal}_status"] == RECOMMEND
    counts = pd.DataFrame({"level0": is_rec & (in_module[f"{goal}_level"] == 0),
                           "any": is_rec}).groupby(
        [in_module["course_id"], in_module["student_id"]]).sum()
    keys = counts.sort_values(["level0", "any"], ascending=False, kind="stable").index
    options = [f"{student} ({course})" for course, student in keys]
    choice = c2.selectbox("Student", options, key="route_student")
    student_id = int(choice.split(" ")[0])
    rows = in_module[in_module["student_id"] == student_id].sort_values("week")
    weeks = rows["week"].tolist()
    recommended = rows[rows[f"{goal}_status"] == RECOMMEND].sort_values(
        [f"{goal}_level", "week"])["week"].tolist()
    first = weeks.index(recommended[0]) if recommended else 0
    week = c3.selectbox("Week", weeks, index=first, key="route_week")
    return rows[rows["week"] == week].iloc[0]


def step_text(step) -> str:
    if step.status != RECOMMEND:
        return "No clear winner. Keep your current plan."
    return f"Lift {pct(step.lift)} (95% range {pct(step.ci_low)} to {pct(step.ci_high)})."


def why_section(goal: str, row: pd.Series, state: State, action, level: int, cfg) -> None:
    rows_at_level = candidate_rows(goal, state, level)
    if rows_at_level.empty:
        st.info("No comparison data exists for this situation.")
        return
    st.plotly_chart(lift_chart(rows_at_level, action,
                               f"Lift per activity this week, back-off level {level} "
                               "(95% range)"), width="stretch", key="why_chart")
    rows_at_level = rows_at_level.sort_values("lift", ascending=False)
    supported = rows_at_level[COUNT_COLS].min(axis=1) >= cfg.min_count
    st.dataframe(pd.DataFrame({
        "activity": [label(a) for a in rows_at_level["action"]],
        "lift": rows_at_level["lift"].map(pct),
        "95% range": [f"{pct(lo)} to {pct(hi)}" for lo, hi in
                      zip(rows_at_level["ci_low"], rows_at_level["ci_high"], strict=True)],
        "used it": [count_text(v, cfg) for v in rows_at_level["n_did"]],
        "did not": [count_text(v, cfg) for v in rows_at_level["n_did_not"]],
        "enough data": ["yes" if s else "no" for s in supported],
    }), hide_index=True, width="stretch")
    st.caption("Counts are student-weeks. A count below "
               f"{cfg.display_min_count} shows as 'fewer than {cfg.display_min_count}'.")

    # Teacher audit for the student's own level 0 cell.
    audit = load_table(APP_DIR, f"audit_{goal}.parquet")
    cell = audit
    for name in LEVELS[0]:
        cell = cell[cell[name] == row[name]]
    if cell.empty:
        return
    actions = sorted(cell["action"].unique())
    first = actions.index(action) if action in actions else 0
    picked_action = st.selectbox("Check one activity by hand", actions, index=first,
                                 format_func=label, key="why_audit_action")
    picked = cell[cell["action"] == picked_action].sort_values(
        "next_effort_band", key=lambda c: c.map(EFFORT_ORDER))
    view = pd.DataFrame({"next-week effort": picked["next_effort_band"]})
    for col in ("n1", "k1", "n0", "k0"):
        view[col] = [count_text(v, cfg) for v in picked[col]]
    view["p1"] = picked["p1"].map(lambda v: "hidden" if pd.isna(v) else f"{v:.1%}")
    view["p0"] = picked["p0"].map(lambda v: "hidden" if pd.isna(v) else f"{v:.1%}")
    st.dataframe(view, hide_index=True, width="stretch")
    st.caption("n1, k1: student-weeks that used it, and how many reached the goal. n0, k0: "
               "student-weeks that did not. p1 and p0 are smoothed goal rates. The lift is the "
               "mean of p1 minus p0 over the effort bands, with weight n1 times n0 divided by "
               f"(n1 plus n0). Rates are hidden where a count is below {cfg.display_min_count}.")


def route_tab(cfg) -> None:
    students = load_table(APP_DIR, "students.parquet")
    plan = plan_data(APP_DIR)
    st.write("Pick a student, a week, a goal and the effort to plan for. LiftPath plans the "
             "next weeks with students who were in the same situation and studied about as "
             "much.")
    c1, c2 = st.columns(2)
    goal = c1.radio("Goal", list(GOAL_NAMES), format_func=GOAL_NAMES.get, horizontal=True,
                    key="route_goal")
    effort = c2.radio("Effort to plan for", list(EFFORT_CHOICES),
                      format_func=EFFORT_CHOICES.get, horizontal=True, key="route_effort")
    row = pick_student(students, goal)
    state = State(row["module"], row["week_block"], row["score_band"], row["effort_band"])
    st.caption(f"Student state: {situation(state, 0).strip('()')}. Course {row['course_id']}, "
               f"week {row['week']}.")
    if plan is None:
        st.info("No route data. Run `make plan` and then `make app-data`.")
        return
    projector, schedule = plan

    recovery = load_table(APP_DIR, "recovery_points.parquet")
    card = rescue_card(row, recovery, schedule, cfg) if recovery is not None else None
    if card is not None:
        with st.container(border=True):
            st.markdown(f"**First, go back: {card.label}** (score {card.score:.0f} on the last "
                        "assessment)")
            st.write(card.rationale)
            if card.items:
                st.caption("Old items to revisit: " + ", ".join(map(str, card.items)))

    route = plan_route(row, goal, lift_tables(goal), projector, schedule, cfg,
                       None if effort == "same" else effort)
    if not route.steps:
        st.info(route.stop_reason)
        return
    st.subheader("Your route")
    for col, step in zip(st.columns(len(route.steps)), route.steps, strict=True):
        with col.container(border=True):
            st.markdown(f"**Week {step.week}**")
            st.write(label(step.action) if step.status == RECOMMEND else KEEP_LABEL)
            st.caption(step_text(step))
            if step.items:
                st.caption("Items: " + ", ".join(map(str, step.items)))
            if step.week != route.steps[0].week:
                st.caption(f"Projected score band: {step.score_band}")
    st.caption(f"{route.stop_reason} {ITEM_NOTE} Effort planned: {route.effort}. "
               f"Score bands after the first week: {PROJECTION_NOTE[0].lower()}"
               f"{PROJECTION_NOTE[1:]}")

    if not np.isnan(route.projected_route):
        st.plotly_chart(projection_chart(route, GOAL_NAMES[goal].lower()), width="stretch",
                        key="route_projection")
        gap = 100 * (route.projected_route - route.projected_typical)
        st.caption(f"Route minus typical path: {gap:+.2f} pp. {PROJECTION_NOTE}")

    first = route.steps[0]
    action = first.action if first.status == RECOMMEND else None
    lines = trap_lines(row, goal, action)
    if lines:
        st.subheader("What common advice says")
        for line in lines:
            st.write(line)

    with st.expander("Why?"):
        stored = row[f"{goal}_level"]
        level = first.level if first.level >= 0 else (0 if pd.isna(stored) else int(stored))
        why_section(goal, row, state, action, level, cfg)


def simulator_tab() -> None:
    results = load_table(APP_DIR, "sim_results.parquet")
    estimates = load_table(APP_DIR, "sim_estimates.parquet")
    if results is None or estimates is None:
        st.info("No simulator results. Run `make sim` and then `make app-data`.")
        return
    st.write("Simulated students learn week by week. Each policy advises a new cohort, then "
             "learns from the outcomes of its own cohorts. In the hidden confounder world, one "
             "activity only looks useful, because the same hidden trait drives both its use "
             "and success.")
    c1, c2, c3 = st.columns([1, 2, 1])
    world = c1.selectbox("World", list(WORLD_NAMES), format_func=lambda w: WORLD_NAMES[w],
                         key="sim_world")
    policies = c2.multiselect("Policies", list(POLICIES), default=list(POLICIES),
                              format_func=POLICY_NAMES.get, key="sim_policies")
    last = int(results["cohort"].max())
    upto = (c3.slider("Show cohorts up to", 1, last, last, key="sim_cohort") if last > 1
            else last)
    in_world = results[results["world"] == world]
    st.plotly_chart(sim_pass_rate_chart(in_world, policies or ["liftpath"], upto, world),
                    width="stretch", key="sim_pass_chart")
    final = in_world[in_world["cohort"] == last].set_index("policy")["pass_rate"]
    table = pd.DataFrame({"policy": [POLICY_NAMES[p] for p in POLICIES],
                          f"pass rate, cohort {last}": [f"{final[p]:.1%}" for p in POLICIES]})
    if last >= 2:
        means = (in_world[in_world["cohort"].between(2, last)].groupby("policy")["pass_rate"]
                 .mean())
        table[f"mean pass rate, cohorts 2 to {last}"] = [f"{means[p]:.1%}" for p in POLICIES]
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("LiftPath + explore swings from cohort to cohort, so the last cohort alone can "
               "mislead. Compare the means too.")

    st.subheader("How the estimates converge")
    c1, c2 = st.columns(2)
    in_world = estimates[estimates["world"] == world]
    c1.plotly_chart(sim_estimates_chart(in_world, "quiz"), width="stretch", key="sim_est_quiz")
    c2.plotly_chart(sim_estimates_chart(in_world, "resource"), width="stretch",
                    key="sim_est_resource")
    st.caption("Lines: 95% range. The experimental estimate comes from the explored "
               "recommendations. It sits above the true effect, because the explore design "
               "itself adds an upward bias. In the hidden confounder world, LiftPath + explore "
               "moves to quiz only in the cohorts where this bias pushes the range above zero. "
               "So its win there depends on that bias.")


def try_it_tab(meta: dict, cfg) -> None:
    st.info(DEMO_BANNER)
    folder = live_dir()
    con = live_store(str(folder / Path(cfg.live_db_path).name))
    cutoffs = load_table(APP_DIR, CUTOFF_FILE)
    if cutoffs is None:
        st.info("No effort cutoffs. Run `make app-data`.")
        return
    candidates = meta["candidates"]
    if "live_rng" not in st.session_state:
        st.session_state["live_rng"] = np.random.default_rng(cfg.seed)

    with st.form("live_add", border=True):
        c1, c2 = st.columns(2)
        new_id = c1.text_input("New student id", value="demo1", key="live_new_id")
        new_module = c2.selectbox("Module", sorted(cutoffs["module"].unique()),
                                  key="live_new_module")
        if st.form_submit_button("Add student"):
            add_student(con, new_id.strip(), new_module)
    students = pd.read_sql_query("SELECT student_id, module FROM students ORDER BY created", con)
    if students.empty:
        st.caption("Add a student to start.")
        return
    c1, c2, c3 = st.columns(3)
    student = c1.selectbox("Student", students["student_id"], key="live_student")
    module = students.set_index("student_id").loc[student, "module"]
    weeks = sorted(cutoffs.loc[cutoffs["module"] == module, "week"])
    week = c2.selectbox("Week", weeks, key="live_week")
    goal = c3.radio("Goal", list(GOAL_NAMES), format_func=GOAL_NAMES.get, horizontal=True,
                    key="live_goal")

    c1, c2 = st.columns(2)
    with c1.form("live_activity", border=True):
        item_type = st.selectbox("Activity", candidates, format_func=label,
                                 key="live_item_type")
        clicks = st.number_input("Clicks", min_value=1, value=10, key="live_clicks")
        if st.form_submit_button("Log activity"):
            log_activity(con, student, week, item_type, clicks)
    with c2.form("live_score", border=True):
        number = st.number_input("Assessment number", min_value=1, value=1, key="live_ass_no")
        score = st.number_input("Score", min_value=0, max_value=100, value=60,
                                key="live_score_value")
        if st.form_submit_button("Log score"):
            log_score(con, student, number, week, score)

    if st.button("Get advice for next week", key="live_advise"):
        out = advise(con, student, week, goal, lift_tables(goal), candidates, cutoffs, cfg,
                     st.session_state["live_rng"])
        st.subheader(headline(out["status"], out["action"]))
        s = out["state"]
        st.caption(f"State: {s['week_block']} weeks, score {s['score_band']}, effort "
                   f"{s['effort_band']}.")
        if out["status"] == EXPLORE:
            st.write(f"This advice explores. LiftPath picks a random activity "
                     f"{cfg.sim_explore_share:.0%} of the time, so that it can learn what "
                     "works.")
        elif out["lift"] is not None:
            st.write(f"Lift {out['lift']:+.0%} (95% range {out['ci_low']:+.0%} to "
                     f"{out['ci_high']:+.0%}).")

    with st.form("live_outcome", border=True):
        result = st.selectbox("Final result of this student", FINAL_RESULTS,
                              key="live_result")
        if st.form_submit_button("Save final result"):
            set_outcome(con, student, result)
    points = ROOT / "data" / "processed" / meta["scope"] / "decision_points.parquet"
    if points.exists():
        if st.button("Refresh lift tables with the live students", key="live_refresh"):
            train = pd.read_parquet(points)
            refresh_tables(con, train[train["split"] == "train"], candidates, cutoffs, cfg,
                           folder)
            cached_lift_tables.clear()
            st.success("The lift tables now include the live students with a final result.")
    else:
        st.caption("Refresh is off: it needs the train points from the full build, and this "
                   "copy has only the app data.")
    log = pd.read_sql_query("SELECT student_id, week, status, action, explored, lift "
                            "FROM advice ORDER BY created DESC", con)
    if not log.empty:
        st.dataframe(log, hide_index=True, width="stretch")


def rescue_tab(meta: dict, cfg) -> None:
    edges = load_table(APP_DIR, "rescue_edges.parquet")
    info = load_json(APP_DIR, "rescue_meta.json")
    if edges is None or info is None or edges.empty:
        st.info("No rescue edges. Run `make rescue` and then `make app-data`.")
        return
    st.write("After a low score, which activity types helped train students pass the next "
             "assessment? Students are compared with others of the same effort before the next "
             "assessment.")
    solid_modules = sorted(edges.loc[edges["style"] == SOLID, "module"].unique())
    modules = sorted(edges["module"].unique())
    first = modules.index(solid_modules[0]) if solid_modules else 0
    module = st.selectbox("Module", modules, index=first, key="rescue_module")
    fig = rescue_figure(edges, module, rescue_note(info))
    fig.update_layout(width=None)
    st.plotly_chart(fig, width="stretch", key="rescue_chart")
    none = sorted(set(meta.get("modules", [])) - set(modules))
    if none:
        st.caption(f"No supported edge: {', '.join(none)}.")
    found = keystone(build_graph(edges[edges["module"] == module]))
    if found is None:
        st.caption(f"{module} has no solid edge, so it has no keystone.")
    else:
        st.caption(f"Keystone in {module}: {found}, the type with the highest summed lift over "
                   "solid edges. With one or two solid edges per type and overlapping ranges, "
                   "the choice of keystone is not clear, and the shuffle check above says the "
                   "solid edges can be chance.")
    items = load_table(APP_DIR, "rescue_items.parquet")
    if items is not None:
        items = items[items["course_id"].str.startswith(f"{module}_")]
        if not items.empty:
            st.dataframe(pd.DataFrame({
                "assessment": items["assessment_id"], "activity": items["action"].map(label),
                "old item": items["item_id"], "recovered students who revisited it":
                    [count_text(v, cfg) for v in items["n_students"]],
            }), hide_index=True, width="stretch")


def eval_section(cfg) -> None:
    results = load_json(APP_DIR, "eval_results.json")
    if results is None:
        st.info("No evaluation results. Run `make eval` and then `make app-data`.")
        return
    goal = st.radio("Goal", list(results["goals"]), format_func=GOAL_NAMES.get,
                    horizontal=True, key="evidence_goal")
    data = results["goals"][goal]
    table = pd.DataFrame(data["results"])
    st.write("Follower lift compares test students who did the recommended activity next week "
             "with students who did not, in the same situation and effort band. Random advice "
             "also shows a positive follower lift, because engaged students do more of "
             "everything. Net lift subtracts that bias floor.")
    lp = table.set_index("name").loc["liftpath"]
    m1, m2, m3 = st.columns(3)
    m1.metric("LiftPath net lift", pct(lp["net_lift"]),
              help=f"95% range {pct(lp['net_ci_low'])} to {pct(lp['net_ci_high'])}")
    m2.metric("Recommend share", f"{lp['coverage']:.0%}")
    shares = data["liftpath_status_shares"]
    m3.metric("Gets an answer (not abstain)", f"{1 - shares[ABSTAIN]:.0%}")
    for metric, title in (("lift", "Follower lift"), ("net_lift", "Net lift (minus random)")):
        low, high = ("ci_low", "ci_high") if metric == "lift" else ("net_ci_low", "net_ci_high")
        rows = pd.DataFrame({"action": table["name"], "lift": table[metric],
                             "ci_low": table[low], "ci_high": table[high]})
        st.plotly_chart(lift_chart(rows, "liftpath", f"{title}, goal: {GOAL_NAMES[goal]} "
                                   "(95% range)", names=str), width="stretch",
                        key=f"evidence_{metric}")
    if "disagreement" in data:
        d = data["disagreement"]
        st.caption(f"On the common test points, LiftPath gives a different action than "
                   f"user_cf at {d['user_cf']:.0%} of them, and than raw_success at "
                   f"{d['raw_success']:.0%}.")
    if "ref_minus" in table:
        st.markdown("**LiftPath minus each recommender** (paired bootstrap; above zero means "
                    "LiftPath is better)")
        others = table[table["name"] != "liftpath"]
        st.dataframe(pd.DataFrame({
            "recommender": others["name"],
            "all test points": others["ref_minus"].map(pct),
            "95% range": [f"{pct(a)} to {pct(b)}" for a, b in
                          zip(others["ref_minus_ci_low"], others["ref_minus_ci_high"],
                              strict=True)],
            "common subset": others["common_ref_minus"].map(pct),
            "common 95% range": [f"{pct(a)} to {pct(b)}" for a, b in
                                 zip(others["common_ref_minus_ci_low"],
                                     others["common_ref_minus_ci_high"], strict=True)],
        }), hide_index=True, width="stretch")


def fairness_section(cfg) -> None:
    report = load_table(APP_DIR, "fairness.parquet")
    if report is None:
        st.info("No fairness results. Run `make eval` and then `make app-data`.")
        return
    st.write("LiftPath results per group on test data, goal: pass. A hollow dot marks a small "
             f"sample (fewer than {SMALL_SAMPLE_STUDENTS} students).")
    rows = report.iloc[::-1]
    labels = [f"{r.attribute}: {r.group}" for r in rows.itertuples()]
    lift, low, high = (100 * rows[c] for c in ("lift", "ci_low", "ci_high"))
    fig = go.Figure(go.Scatter(
        x=lift, y=labels, mode="markers",
        marker={"size": 10, "line": {"color": BLUE, "width": 2},
                "color": [(HOLLOW if s else BLUE) for s in rows["small_sample"]]},
        error_x={"type": "data", "array": high - lift, "arrayminus": lift - low,
                 "color": BLUE},
        hovertemplate="%{y}: %{x:+.1f} pp<extra></extra>"))
    fig.update_layout(template="simple_white", height=120 + 26 * len(rows),
                      xaxis_tickformat="+.1f", xaxis_ticksuffix=" pp",
                      title="Follower lift by group (95% range)",
                      margin={"l": 10, "r": 10, "t": 50, "b": 30})
    fig.update_xaxes(gridcolor=GRID, showgrid=True, zeroline=True, zerolinecolor=MUTED)
    st.plotly_chart(fig, width="stretch", key="evidence_fairness")
    st.dataframe(pd.DataFrame({
        "attribute": report["attribute"], "group": report["group"],
        "students": [count_text(v, cfg) for v in report["n_students"]],
        "coverage": report["coverage"].map("{:.0%}".format),
        "recommend share": report["recommend_share"].map("{:.0%}".format),
        "follower lift": report["lift"].map(pct),
        "95% range": [f"{pct(a)} to {pct(b)}" for a, b in
                      zip(report["ci_low"], report["ci_high"], strict=True)],
        "note": ["small sample" if s else "" for s in report["small_sample"]],
    }), hide_index=True, width="stretch")


def evidence_tab(cfg) -> None:
    headline_metrics()
    st.subheader("Real-data evaluation")
    eval_section(cfg)
    st.subheader("Fairness")
    fairness_section(cfg)
    truth = Path(APP_DIR) / "figures" / "synthetic_truth.png"
    if truth.exists():
        st.subheader("Test with a known answer (synthetic data)")
        st.write("Follower lift can reward activities that busy students do anyway. Synthetic "
                 "data has a known truth: only quizzes help, and forum use only follows effort. "
                 "LiftPath sends none of its recommendations to the forum. Raw success sends "
                 "43.5% of its picks there.")
        st.image(str(truth), width="stretch")


def teacher_context(meta: dict, cfg) -> TeacherContext:
    """The teacher view uses the same lift tables as the route (live after a refresh)."""
    return TeacherContext(
        students=load_table(APP_DIR, "students.parquet"),
        recovery=load_table(APP_DIR, "recovery_points.parquet"),
        tables_for=lift_tables, plan=plan_data(APP_DIR), cfg=cfg,
        settings_file=prefs_path(cfg, live_dir()), candidates=list(meta["candidates"]))


def main() -> None:
    st.set_page_config(page_title="LiftPath", layout="wide")
    meta = load_json(APP_DIR, "meta.json")
    if meta is None:
        st.title("LiftPath")
        st.error(f"No app data in {APP_DIR}. Run `make app-data`.")
        return
    cfg = app_config(meta)
    header()
    teacher = teacher_context(meta, cfg)
    tabs = st.tabs(TABS)
    with tabs[0]:
        teacher_tab(teacher)
    with tabs[1]:
        st.caption("The tabs from here to Evidence show how LiftPath finds each suggestion.")
        route_tab(cfg)
    with tabs[2]:
        simulator_tab()
    with tabs[3]:
        try_it_tab(meta, cfg)
    with tabs[4]:
        rescue_tab(meta, cfg)
    with tabs[5]:
        evidence_tab(cfg)
    with tabs[6]:
        settings_tab(teacher)
    st.caption(f"Data: Open University Learning Analytics Dataset (OULAD), CC BY 4.0. "
               f"Scope: {meta['scope']}. The data is observational: lift is evidence, not proof "
               "of cause. LiftPath supports decisions. It does not make them.")


main()
