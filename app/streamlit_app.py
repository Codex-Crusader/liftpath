"""LiftPath app. Reads the files that `make app-data` writes (APP_DATA_DIR, default data/app)."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from liftpath.config import load_config
from liftpath.fairness import SMALL_SAMPLE_STUDENTS
from liftpath.lift import ABSTAIN, LEVELS, NO_CLEAR_WINNER, RECOMMEND
from liftpath.live import load_lift_tables
from liftpath.recommend import State, label, recommend, show_count, situation
from liftpath.recover import explain_recovery
from liftpath.style import BLUE, GRID, MUTED
from liftpath.trap import trap_lines

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = os.environ.get("APP_DATA_DIR", str(ROOT / "data" / "app"))
GOAL_NAMES = {"goal_pass": "Pass", "goal_distinction": "Distinction"}
COUNT_COLS = ["n_did", "n_did_not"]
HOLLOW = "rgba(0,0,0,0)"
EFFORT_ORDER = {"low": 0, "mid": 1, "high": 2}
PITCH = "Not what students like you did. What helped students like you."


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
def lift_tables(goal: str) -> dict[int, pd.DataFrame]:
    """The live tables when they exist (BUILD2 Phase D), else the app tables."""
    return load_lift_tables(goal, Path(APP_DIR))


def app_config(meta: dict):
    return replace(load_config(ROOT / "config.yaml"), **meta["config"])


def count_text(value, cfg) -> str:
    return f"fewer than {cfg.display_min_count}" if pd.isna(value) else show_count(int(value), cfg)


def pct(value) -> str:
    """A difference of two rates, in percentage points."""
    return "" if pd.isna(value) else f"{100 * value:+.1f} pp"


def headline(status: str, action) -> str:
    if status == RECOMMEND:
        return f"Next step: {label(action)}"
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
    cells = LEVELS[level]
    values = {"module": state.module, "week_block": state.week_block,
              "score_band": state.score_band, "effort_band": state.effort_band}
    mask = pd.Series(True, index=table.index)
    for col in cells:
        mask &= table[col] == values[col]
    return table[mask]


def student_tab(meta: dict, cfg) -> None:
    students = load_table(APP_DIR, "students.parquet")
    st.write("Pick a test student and a week. LiftPath compares students in the same situation "
             "who studied about as much the next week. It recommends the activity with the "
             "highest measured lift, but only if the 95% range is above zero.")
    c1, c2, c3, c4 = st.columns(4)
    goal = c4.radio("Goal", list(GOAL_NAMES), format_func=GOAL_NAMES.get)
    module = c1.selectbox("Module", sorted(students["module"].unique()))
    in_module = students[students["module"] == module]
    # Students with the most level 0 recommendations come first, so the demo opens on a card
    # with the most specific evidence.
    is_rec = in_module[f"{goal}_status"] == RECOMMEND
    counts = pd.DataFrame({"level0": is_rec & (in_module[f"{goal}_level"] == 0),
                           "any": is_rec}).groupby(
        [in_module["course_id"], in_module["student_id"]]).sum()
    keys = counts.sort_values(["level0", "any"], ascending=False, kind="stable").index
    options = [f"{student} ({course})" for course, student in keys]
    choice = c2.selectbox("Student", options)
    student_id = int(choice.split(" ")[0])
    rows = in_module[in_module["student_id"] == student_id].sort_values("week")
    weeks = rows["week"].tolist()
    recommended = rows[rows[f"{goal}_status"] == RECOMMEND].sort_values(
        [f"{goal}_level", "week"])["week"].tolist()
    first = weeks.index(recommended[0]) if recommended else 0
    week = c3.selectbox("Week", weeks, index=first)
    row = rows[rows["week"] == week].iloc[0]

    state = State(row["module"], row["week_block"], row["score_band"], row["effort_band"])
    rec = recommend(state, goal, lift_tables(goal), cfg)
    action = rec.estimate.action if rec.estimate else None
    st.subheader(headline(rec.status, action))
    st.write(rec.rationale)
    st.caption(f"Student state: {situation(state, 0).strip('()')}. "
               f"Course {row['course_id']}, week {week}.")
    lines = trap_lines(row, goal, action if rec.status == RECOMMEND else None)
    if lines:
        st.markdown("**What common advice says**")
        for line in lines:
            st.write(line)

    level = row[f"{goal}_level"]
    level = 0 if pd.isna(level) else int(level)
    rows_at_level = candidate_rows(goal, state, level)
    if rows_at_level.empty:
        st.info("No comparison data exists for this situation.")
        return
    st.plotly_chart(lift_chart(rows_at_level, action,
                               f"Lift per activity, back-off level {level} (95% range)"),
                    width="stretch")
    rows_at_level = rows_at_level.sort_values("lift", ascending=False)
    supported = (rows_at_level[COUNT_COLS].min(axis=1) >= cfg.min_count)
    table = pd.DataFrame({
        "activity": [label(a) for a in rows_at_level["action"]],
        "lift": rows_at_level["lift"].map(pct),
        "95% range": [f"{pct(lo)} to {pct(hi)}" for lo, hi in
                      zip(rows_at_level["ci_low"], rows_at_level["ci_high"], strict=True)],
        "used it": [count_text(v, cfg) for v in rows_at_level["n_did"]],
        "did not": [count_text(v, cfg) for v in rows_at_level["n_did_not"]],
        "enough data": ["yes" if s else "no" for s in supported],
    })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("Counts are student-weeks. A count below "
               f"{cfg.display_min_count} shows as 'fewer than {cfg.display_min_count}'.")


def recovery_tab(cfg) -> None:
    points = load_table(APP_DIR, "recovery_points.parquet")
    st.write("After a low score, which earlier material helps a student pass the next "
             "assessment? LiftPath compares students with a similar low score who studied about "
             "as much before the next assessment.")
    c1, c2, c3 = st.columns(3)
    course = c1.selectbox("Course", sorted(points["course_id"].unique()))
    in_course = points[points["course_id"] == course]
    assessment = c2.selectbox("Assessment", sorted(in_course["assessment_id"].unique()))
    in_assessment = in_course[in_course["assessment_id"] == assessment]
    student_id = c3.selectbox("Student with a low score", sorted(in_assessment["student_id"]))
    row = in_assessment[in_assessment["student_id"] == student_id].iloc[0]
    st.subheader(headline(row["status"], row["action"]).replace("Next step", "Go back to"))
    st.write(f"Score on this assessment: {row['score']:.0f}.")
    st.write(explain_recovery(row, row["module"], row["low_band"], cfg))


def eval_tab(cfg) -> None:
    results = load_json(APP_DIR, "eval_results.json")
    if results is None:
        st.info("No evaluation results. Run `make eval` and then `make app-data`.")
        return
    goal = st.radio("Goal ", list(results["goals"]), format_func=GOAL_NAMES.get,
                    horizontal=True)
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
        fig = lift_chart(rows, "liftpath", f"{title}, goal: {GOAL_NAMES[goal]} (95% range)",
                         names=str)
        st.plotly_chart(fig, width="stretch")

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

    truth = Path(APP_DIR) / "figures" / "synthetic_truth.png"
    if truth.exists():
        st.markdown("**Test with a known answer (synthetic data)**")
        st.write("Follower lift can reward activities that busy students do anyway. Synthetic "
                 "data has a known truth: only quizzes help, and forum use only follows effort. "
                 "LiftPath sends none of its recommendations to the forum. Raw success sends "
                 "43.5% of its picks there.")
        st.image(str(truth), width="stretch")


def fairness_tab(cfg) -> None:
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
    st.plotly_chart(fig, width="stretch")
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


def audit_tab(cfg) -> None:
    st.write("Check one lift by hand. Pick a situation and an activity. The table shows the "
             "counts in each next-week effort band. p1 and p0 are the smoothed goal rates of "
             "students who used the activity and students who did not.")
    goal = st.radio("Goal  ", list(GOAL_NAMES), format_func=GOAL_NAMES.get, horizontal=True)
    audit = load_table(APP_DIR, f"audit_{goal}.parquet")
    cols = st.columns(5)
    picked = audit
    for col, name in zip(cols[:4], LEVELS[0], strict=True):
        value = col.selectbox(name.replace("_", " "), sorted(picked[name].unique()))
        picked = picked[picked[name] == value]
    action = cols[4].selectbox("activity", sorted(picked["action"].unique()), format_func=label)
    picked = picked[picked["action"] == action]
    picked = picked.sort_values("next_effort_band", key=lambda c: c.map(EFFORT_ORDER))
    view = pd.DataFrame({"next-week effort": picked["next_effort_band"]})
    for col in ("n1", "k1", "n0", "k0"):
        view[col] = [count_text(v, cfg) for v in picked[col]]
    view["p1"] = picked["p1"].map(lambda v: "hidden" if pd.isna(v) else f"{v:.1%}")
    view["p0"] = picked["p0"].map(lambda v: "hidden" if pd.isna(v) else f"{v:.1%}")
    st.dataframe(view, hide_index=True, width="stretch")
    st.caption(f"n1, k1: student-weeks that used it, and how many reached the goal. n0, k0: "
               f"student-weeks that did not. Rates are hidden where a count is below "
               f"{cfg.display_min_count}.")
    table = lift_tables(goal)[0]
    cell = table[table["action"] == action]
    for name, value in zip(LEVELS[0], [picked[c].iloc[0] for c in LEVELS[0]], strict=True):
        cell = cell[cell[name] == value]
    if not cell.empty:
        r = cell.iloc[0]
        st.write(f"Lift for this situation: {pct(r['lift'])} (95% range {pct(r['ci_low'])} "
                 f"to {pct(r['ci_high'])}). It is the weighted mean of p1 minus p0 over the "
                 "effort bands, with weight n1 times n0 divided by (n1 plus n0).")


def main() -> None:
    st.set_page_config(page_title="LiftPath", layout="wide")
    meta = load_json(APP_DIR, "meta.json")
    st.title("LiftPath")
    st.caption(PITCH)
    if meta is None:
        st.error(f"No app data in {APP_DIR}. Run `make app-data`.")
        return
    cfg = app_config(meta)
    tabs = st.tabs(["Student", "Recovery", "Evaluation", "Fairness", "Teacher audit"])
    with tabs[0]:
        student_tab(meta, cfg)
    with tabs[1]:
        recovery_tab(cfg)
    with tabs[2]:
        eval_tab(cfg)
    with tabs[3]:
        fairness_tab(cfg)
    with tabs[4]:
        audit_tab(cfg)
    st.caption(f"Data: Open University Learning Analytics Dataset (OULAD), CC BY 4.0. "
               f"Scope: {meta['scope']}. The data is observational: lift is evidence, not proof "
               "of cause. LiftPath supports decisions. It does not make them.")


main()
