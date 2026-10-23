"""Write the slide figures to reports/slides/ as 1600 x 900 PNGs (BUILD2 Phase G).

Reads only data/app, so the figures show what the app shows. Kaleido renders with the
installed Chrome.
"""

import json
import textwrap
from dataclasses import replace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from liftpath.app_charts import WORLD_NAMES, sim_estimates_chart, sim_pass_rate_chart
from liftpath.config import load_config
from liftpath.engine import app_plan
from liftpath.figures import POLICY_NAMES
from liftpath.lift import LEVELS, RECOMMEND, point_lifts
from liftpath.live import load_lift_tables
from liftpath.paths import APP_DIR, REPORTS_DIR, TMP_DIR
from liftpath.recommend import label
from liftpath.rescue import SOLID, rescue_figure, rescue_note
from liftpath.route import KEEP_LABEL, PROJECTION_NOTE, plan_route, rescue_card
from liftpath.sim import POLICIES
from liftpath.style import BLUE, GRID, METHOD_COLORS, MUTED, SURFACE, TEXT, TEXT_SECONDARY

OUT_DIR = REPORTS_DIR / "slides"
WIDTH, HEIGHT = 1600, 900
FONT, TITLE_FONT, NOTE_FONT, CARD_FONT = 22, 32, 20, 19
NOTE_CHARS = 125
GOAL = "goal_pass"
# Fixed demo students, chosen in Phase G (see PROGRESS.md).
ROUTE_EXAMPLE = {"student_id": 388259, "course_id": "GGG_2014J", "week": 31}
TRAP_EXAMPLE = {"student_id": 334441, "course_id": "AAA_2014J", "week": 36}
HOLLOW = "rgba(0,0,0,0)"
EFFORT_ORDER = {"low": 0, "mid": 1, "high": 2}
CARD_TOP, CARD_BOTTOM = 0.86, 0.50


def slide(fig: go.Figure, title: str, note: str = "", bottom: int = 110,
          chars: int = NOTE_CHARS) -> go.Figure:
    """Large fonts and a note under the plot, wrapped to chars per line."""
    note = "<br>".join(line for part in note.split("<br>")
                       for line in textwrap.wrap(part, chars))
    fig.update_layout(
        title={"text": title, "x": 0.02, "font": {"size": TITLE_FONT}},
        width=WIDTH, height=HEIGHT, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font={"size": FONT, "color": TEXT},
        margin={"l": 60, "r": 60, "t": 100, "b": bottom})
    if note:
        fig.add_annotation(x=0, y=0, xref="paper", yref="paper", yshift=-bottom + 15,
                           xanchor="left", yanchor="bottom", showarrow=False, align="left",
                           text=note, font={"size": NOTE_FONT, "color": TEXT_SECONDARY})
    return fig


def save(fig: go.Figure, name: str) -> Path:
    path = OUT_DIR / name
    fig.write_image(path, width=WIDTH, height=HEIGHT, scale=1)
    print(f"wrote {path}")
    return path


def find_point(students: pd.DataFrame, example: dict) -> pd.Series:
    mask = pd.Series(True, index=students.index)
    for key, value in example.items():
        mask &= students[key] == value
    return students[mask].iloc[0]


def card(fig: go.Figure, x0: float, x1: float, lines: list[str], color: str) -> None:
    fig.add_shape(type="rect", xref="paper", yref="paper", x0=x0, x1=x1, y0=CARD_BOTTOM,
                  y1=CARD_TOP, line={"color": color, "width": 3}, fillcolor="white")
    fig.add_annotation(x=(x0 + x1) / 2, y=(CARD_TOP + CARD_BOTTOM) / 2, xref="paper",
                       yref="paper", xanchor="center", yanchor="middle", showarrow=False,
                       align="center", text="<br>".join(lines), font={"size": CARD_FONT})


def pp_range(lift, low, high) -> str:
    return f"lift {100 * lift:+.1f} pp<br>range {100 * low:+.1f}<br>to {100 * high:+.1f}"


def route_figure(app: Path, students: pd.DataFrame, tables, cfg) -> go.Figure:
    row = find_point(students, ROUTE_EXAMPLE)
    projector, schedule = app_plan(app)
    route = plan_route(row, GOAL, tables, projector, schedule, cfg)
    rescue = rescue_card(row, pd.read_parquet(app / "recovery_points.parquet"), schedule, cfg)
    fig = go.Figure(go.Bar(
        x=[100 * route.projected_typical, 100 * route.projected_route],
        y=["Typical path", "Your route"], orientation="h", marker_color=[MUTED, BLUE],
        text=[f"{route.projected_typical:.1%}", f"{route.projected_route:.1%}"],
        textposition="outside"))
    fig.update_xaxes(range=[0, 105], ticksuffix="%", gridcolor=GRID, domain=[0.12, 0.95])
    fig.update_yaxes(domain=[0.0, 0.36])
    n_cards = len(route.steps) + (rescue is not None)
    gap, width = 0.015, (1 - 0.015 * (n_cards - 1)) / n_cards
    x = 0.0
    if rescue is not None:
        card(fig, x, x + width, ["<b>First, go back</b>", label(rescue.action),
                                 f"last score {rescue.score:.0f}",
                                 pp_range(rescue.lift, rescue.ci_low, rescue.ci_high)],
             TEXT_SECONDARY)
        x += width + gap
    for step in route.steps:
        lines = [f"<b>Week {step.week}</b>"]
        if step.status == RECOMMEND:
            lines += [label(step.action), pp_range(step.lift, step.ci_low, step.ci_high)]
        else:
            lines += [KEEP_LABEL]
        card(fig, x, x + width, lines, BLUE)
        x += width + gap
    fig.add_annotation(x=0, y=0.43, xref="paper", yref="paper", xanchor="left",
                       showarrow=False, text=f"<b>Projected chance of a pass.</b> "
                                             f"{PROJECTION_NOTE}")
    gap_pp = 100 * (route.projected_route - route.projected_typical)
    return slide(fig, f"A route for student {row['student_id']} ({row['course_id']}), "
                      f"week {row['week']}, goal: pass",
                 f"Route minus typical path: {gap_pp:+.1f} pp. {PROJECTION_NOTE} Each step "
                 "compares students in the same situation with the same next-week effort.")


def matched_lift_figure(app: Path, students: pd.DataFrame, tables, cfg) -> go.Figure:
    """The level 0 audit cell of the route example: goal rates per next-week effort band."""
    row = find_point(students, ROUTE_EXAMPLE)
    action = row[f"{GOAL}_action"]
    audit = pd.read_parquet(app / f"audit_{GOAL}.parquet")
    for col in LEVELS[0]:
        audit = audit[audit[col] == row[col]]
    cell = audit[audit["action"] == action].sort_values(
        "next_effort_band", key=lambda c: c.map(EFFORT_ORDER))
    lift = tables[0]
    for col in LEVELS[0]:
        lift = lift[lift[col] == row[col]]
    lift = lift[lift["action"] == action].iloc[0]
    bands = [f"next-week effort: {b}" for b in cell["next_effort_band"]]
    fig = go.Figure()
    for rate, n, name, color in (("p1", "n1", f"used {label(action)}", BLUE),
                                 ("p0", "n0", f"did not use {label(action)}", MUTED)):
        fig.add_trace(go.Bar(
            x=bands, y=100 * cell[rate], name=name, marker_color=color,
            text=[f"{v:.0%}<br>n = {count_text(c, cfg)}"
                  for v, c in zip(cell[rate], cell[n], strict=True)],
            textposition="outside"))
    weight = cell["n1"] * cell["n0"] / (cell["n1"] + cell["n0"])
    for band, d, w in zip(bands, cell["p1"] - cell["p0"], weight, strict=True):
        fig.add_annotation(x=band, y=112, showarrow=False, font={"size": FONT},
                           text=f"difference {100 * d:+.1f} pp, weight {w:.0f}")
    fig.update_yaxes(range=[0, 120], ticksuffix="%", gridcolor=GRID,
                     title="smoothed pass rate (%)", tickvals=list(range(0, 101, 20)))
    fig.update_layout(barmode="group", legend={"orientation": "h", "y": -0.1})
    return slide(fig, f"Matched lift: {label(action)} for {row['module']}, {row['week_block']} "
                      f"weeks, {row['score_band']} scores, effort {row['effort_band']}",
                 f"Lift = weighted mean of the differences = {100 * lift['lift']:+.1f} pp "
                 f"(95% range {100 * lift['ci_low']:+.1f} to {100 * lift['ci_high']:+.1f} pp). "
                 "Weight = n1 x n0 / (n1 + n0). Students are compared only with students of "
                 "the same next-week effort, so effort alone does not count as lift. n: "
                 "student-weeks.", bottom=200)


def count_text(value, cfg) -> str:
    return (f"fewer than {cfg.display_min_count}" if pd.isna(value) else f"{int(value):,}")


def trap_figure(students: pd.DataFrame, tables, cfg) -> go.Figure:
    row = find_point(students, TRAP_EXAMPLE)
    rows = point_lifts(row.to_frame().T.reset_index(drop=True), tables, cfg)
    picks = {"liftpath": row[f"{GOAL}_action"],
             "user_cf": row[f"{GOAL}_user_cf_action"],
             "raw_success": row[f"{GOAL}_raw_success_action"]}
    rows = rows.sort_values("lift")
    names, colors = [], []
    for action in rows["action"]:
        methods = [m for m, a in picks.items() if a == action]
        names.append(label(action) + (f" ({', '.join(POLICY_NAMES[m] for m in methods)})"
                                      if methods else ""))
        colors.append(METHOD_COLORS[methods[0]] if methods else MUTED)
    lift, low, high = (100 * rows[c].astype(float) for c in ("lift", "ci_low", "ci_high"))
    fig = go.Figure(go.Bar(
        x=lift, y=names, orientation="h", marker_color=colors,
        error_x={"type": "data", "array": high - lift, "arrayminus": lift - low,
                 "color": TEXT_SECONDARY, "thickness": 2}))
    fig.update_xaxes(ticksuffix=" pp", gridcolor=GRID, zeroline=True, zerolinecolor=TEXT,
                     title="lift toward a pass, same next-week effort (95% range)")
    fig.update_yaxes(automargin=True)
    return slide(fig, f"Common advice and helpful advice: student {row['student_id']} "
                      f"({row['course_id']}), week {row['week']}",
                 "user_cf picks what similar students did. raw_success picks what successful "
                 "students did. LiftPath picks the highest matched lift with enough data.",
                 bottom=170, chars=95)


def sim_figure(results: pd.DataFrame, world: str) -> go.Figure:
    rows = results[results["world"] == world]
    last = int(rows["cohort"].max())
    fig = sim_pass_rate_chart(rows, list(POLICIES), last, world)
    fig.update_traces(textfont_size=FONT)
    means = rows[rows["cohort"].between(2, last)].groupby("policy")["pass_rate"].mean()
    note = ("Mean pass rate, cohorts 2 to 5: " + ", ".join(
        f"{POLICY_NAMES[p]} {means[p]:.1%}" for p in means.sort_values(ascending=False).index)
        + ".<br>Synthetic students. LiftPath + explore swings from cohort to cohort, so "
        "compare the means too.")
    return slide(fig, f"Simulator, {WORLD_NAMES[world]}: pass rate by cohort", note,
                 bottom=170)


def convergence_figure(estimates: pd.DataFrame) -> go.Figure:
    rows = estimates[estimates["world"] == "hidden_confounder"]
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.08,
                        subplot_titles=["quiz (true effect)", "resource (no true effect)"])
    for col, action in enumerate(("quiz", "resource"), start=1):
        for trace in sim_estimates_chart(rows, action).data:
            trace.showlegend = col == 1
            fig.add_trace(trace, row=1, col=col)
        fig.add_hline(y=0, line_color=MUTED, row=1, col=col)
    fig.update_yaxes(ticksuffix=" pp", gridcolor=GRID, title_text="effect on pass", col=1)
    fig.update_yaxes(ticksuffix=" pp", gridcolor=GRID)
    fig.update_xaxes(title_text="estimate before the cohort", dtick=1, gridcolor=GRID)
    fig.update_layout(legend={"orientation": "h", "y": -0.17})
    fig.update_annotations(font_size=FONT)
    return slide(fig, "Simulator, hidden confounder world: how the estimates converge",
                 "The experimental estimate sits above the true effect, because the explore "
                 "design adds an upward bias.<br>LiftPath + explore moves to quiz only in the "
                 "cohorts where this bias pushes the range above zero.", bottom=240)


def eval_figure(eval_results: dict) -> go.Figure:
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=["Goal: pass", "Goal: distinction"])
    for col, goal in enumerate(("goal_pass", "goal_distinction"), start=1):
        table = pd.DataFrame(eval_results["goals"][goal]["results"])
        table = table[table["name"] != "random"].iloc[::-1]
        net, low, high = (100 * table[c] for c in ("net_lift", "net_ci_low", "net_ci_high"))
        fig.add_trace(go.Scatter(
            x=net, y=[POLICY_NAMES.get(n, n) for n in table["name"]], mode="markers",
            marker={"size": 18, "color": [METHOD_COLORS[n] for n in table["name"]]},
            error_x={"type": "data", "array": high - net, "arrayminus": net - low,
                     "color": TEXT_SECONDARY, "thickness": 2},
            showlegend=False), row=1, col=col)
    fig.update_xaxes(ticksuffix=" pp", gridcolor=GRID, zeroline=True, zerolinecolor=TEXT,
                     title_text="net lift (95% range)")
    fig.update_annotations(font_size=FONT)
    lp = pd.DataFrame(eval_results["goals"]["goal_pass"]["results"]).set_index("name")
    return slide(fig, "Real data: net lift on test students (OULAD 2014J)",
                 "Net lift: follower lift minus the lift of random advice. LiftPath advises on "
                 f"{lp.loc['liftpath', 'coverage']:.0%} of student-weeks and says 'no clear "
                 "winner' on the rest. On the common subset for pass, LiftPath and raw_success "
                 "are within each other's range. The "
                 "data is observational: lift is evidence, not proof of cause.", bottom=170)


def rescue_slide(app: Path) -> go.Figure:
    edges = pd.read_parquet(app / "rescue_edges.parquet")
    info = json.loads((app / "rescue_meta.json").read_text(encoding="utf-8"))
    module = sorted(edges.loc[edges["style"] == SOLID, "module"].unique())[0]
    fig = rescue_figure(edges, module, rescue_note(info))
    fig.update_layout(width=WIDTH, height=HEIGHT, font={"size": 18},
                      title={"font": {"size": TITLE_FONT}})
    fig.update_traces(textfont_size=18)
    fig.update_annotations(font_size=17)
    return fig


def fairness_figure(app: Path, eval_results: dict) -> go.Figure:
    report = pd.read_parquet(app / "fairness.parquet").iloc[::-1]
    labels = [f"{r.attribute}: {r.group}" for r in report.itertuples()]
    lift, low, high = (100 * report[c] for c in ("lift", "ci_low", "ci_high"))
    fig = go.Figure(go.Scatter(
        x=lift, y=labels, mode="markers",
        marker={"size": 14, "line": {"color": BLUE, "width": 3},
                "color": [HOLLOW if s else BLUE for s in report["small_sample"]]},
        error_x={"type": "data", "array": high - lift, "arrayminus": lift - low,
                 "color": BLUE, "thickness": 2}))
    overall = pd.DataFrame(eval_results["goals"][GOAL]["results"]).set_index("name")
    fig.add_vline(x=100 * overall.loc["liftpath", "lift"], line_dash="dot",
                  line_color=TEXT_SECONDARY)
    fig.update_xaxes(ticksuffix=" pp", gridcolor=GRID, zeroline=True, zerolinecolor=TEXT,
                     title="LiftPath follower lift, goal: pass (95% range)")
    fig.update_yaxes(tickfont_size=17)
    return slide(fig, "Fairness: LiftPath lift by group (test students)",
                 "Dotted line: all test students. Hollow dot: fewer than 200 students.",
                 bottom=130)


def main() -> int:
    app = APP_DIR
    meta = json.loads((app / "meta.json").read_text(encoding="utf-8"))
    cfg = replace(load_config(), **meta["config"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    students = pd.read_parquet(app / "students.parquet")
    for col in (c for c in students if c.endswith("_level")):
        students[col] = students[col].astype(float)
    # The app tables only: a missing folder means no live tables.
    tables = load_lift_tables(GOAL, app, TMP_DIR / "no_live_tables")
    eval_results = json.loads((app / "eval_results.json").read_text(encoding="utf-8"))
    results = pd.read_parquet(app / "sim_results.parquet")
    estimates = pd.read_parquet(app / "sim_estimates.parquet")
    save(route_figure(app, students, tables, cfg), "route_example.png")
    save(trap_figure(students, tables, cfg), "trap_example.png")
    save(matched_lift_figure(app, students, tables, cfg), "matched_lift.png")
    save(sim_figure(results, "standard"), "sim_standard.png")
    save(sim_figure(results, "hidden_confounder"), "sim_hidden.png")
    save(convergence_figure(estimates), "estimate_convergence.png")
    save(eval_figure(eval_results), "eval_real_data.png")
    save(rescue_slide(app), "rescue_map.png")
    save(fairness_figure(app, eval_results), "fairness.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
