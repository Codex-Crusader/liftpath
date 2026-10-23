"""Rescue map (BUILD2 Phase E): which activity types help after a low score, per assessment.

Edges come from train recovery points only. Cell = (module, assessment_id), effort control =
window effort band, support = rescue_min_count on both sides.
"""

import duckdb
import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from liftpath.config import Config
from liftpath.lift import estimate_lifts
from liftpath.recover import ACTIVE_DAY_SQL, WEEK_DAYS
from liftpath.states import action_of
from liftpath.style import BLUE, GRID, MUTED, SURFACE, TEXT, TEXT_SECONDARY

SOLID = "solid"
DASHED = "dashed"
CELL = ["module", "assessment_id"]
ITEMS_PER_EDGE = 3
STRONGEST_PER_LINE = 4
EDGE_COLS = ["module", "course_id", "assessment_id", "due_day", "action", "lift", "ci_low",
             "ci_high", "n_did", "n_did_not", "style"]

ITEMS_SQL = """
SELECT c.course_id, c.assessment_id, c.action, e.item_id, a.item_type,
       count(DISTINCT c.student_id) AS n_students, sum(e.clicks) AS clicks
FROM rescue_cases c
JOIN events e
  ON e.course_id = c.course_id AND e.student_id = c.student_id
 AND e.day > c.due_day AND e.day <= c.next_due_day
JOIN active_days a ON a.course_id = e.course_id AND a.item_id = e.item_id
WHERE a.active_day < c.due_day
GROUP BY ALL
"""


def check_train(points: pd.DataFrame) -> None:
    if (points["split"] == "test").any():
        raise ValueError("Test points must not enter the rescue map.")


def rescue_edges(train: pd.DataFrame, candidates: list[str], cfg: Config) -> pd.DataFrame:
    """Supported positive lifts per (assessment, type). Solid if ci_low > 0, else dashed."""
    check_train(train)
    lifts = estimate_lifts(train, CELL, "effort_band", [f"rev_{a}" for a in candidates],
                           "goal_recover", cfg)
    lifts["action"] = lifts["action"].str.removeprefix("rev_")
    supported = lifts[lifts[["n_did", "n_did_not"]].min(axis=1) >= cfg.rescue_min_count]
    edges = supported[supported["lift"] > 0].copy()
    edges["style"] = np.where(edges["ci_low"] > 0, SOLID, DASHED)
    where = train.drop_duplicates("assessment_id")[["assessment_id", "course_id", "due_day"]]
    return edges.merge(where, on="assessment_id")[EDGE_COLS].reset_index(drop=True)


def null_solid_counts(train: pd.DataFrame, candidates: list[str], cfg: Config,
                      runs: int) -> np.ndarray:
    """Solid edge counts when goal_recover is shuffled within (cell, effort band)."""
    rng = np.random.default_rng(cfg.seed)
    groups = train.groupby([*CELL, "effort_band"]).indices.values()
    counts = []
    for _ in range(runs):
        goal = train["goal_recover"].to_numpy().copy()
        for idx in groups:
            goal[idx] = goal[rng.permutation(idx)]
        edges = rescue_edges(train.assign(goal_recover=goal), candidates, cfg)
        counts.append(int((edges["style"] == SOLID).sum()))
    return np.array(counts)


def rescue_items(con: duckdb.DuckDBPyConnection, train: pd.DataFrame, edges: pd.DataFrame,
                 cfg: Config) -> pd.DataFrame:
    """Per solid edge: the old items of that type that recovered train students revisited most.

    con must have the canonical tables registered.
    """
    check_train(train)
    solid = edges.loc[edges["style"] == SOLID, ["assessment_id", "action"]]
    recovered = train[train["goal_recover"]]
    cases = recovered.merge(solid, on="assessment_id")
    revisited = np.zeros(len(cases), dtype=bool)
    for action in cases["action"].unique():
        rows = (cases["action"] == action).to_numpy()
        revisited[rows] = cases.loc[rows, f"rev_{action}"].to_numpy(bool)
    cases = cases[revisited]
    cases = cases[["course_id", "student_id", "assessment_id", "due_day", "next_due_day",
                   "action"]]
    if cases.empty:
        return pd.DataFrame(columns=["course_id", "assessment_id", "action", "item_id",
                                     "n_students", "clicks", "rank"])
    con.register("rescue_cases", cases)
    con.execute("CREATE OR REPLACE TEMP TABLE active_days AS "
                + ACTIVE_DAY_SQL.format(week_days=WEEK_DAYS))
    items = con.execute(ITEMS_SQL).df()
    con.unregister("rescue_cases")
    items = items[action_of(items["item_type"], cfg) == items["action"]]
    items = items.sort_values(["assessment_id", "action", "n_students", "clicks", "item_id"],
                              ascending=[True, True, False, False, True])
    items = items.groupby(["assessment_id", "action"]).head(ITEMS_PER_EDGE).copy()
    items["rank"] = items.groupby(["assessment_id", "action"]).cumcount() + 1
    return items[["course_id", "assessment_id", "action", "item_id", "n_students", "clicks",
                  "rank"]].reset_index(drop=True)


def type_node(action: str) -> str:
    return f"type:{action}"


def assessment_node(assessment_id: int) -> str:
    return f"assessment:{assessment_id}"


def build_graph(edges: pd.DataFrame) -> nx.Graph:
    """Activity types and assessments as nodes. Edge weight = lift."""
    graph = nx.Graph()
    for row in edges.itertuples():
        graph.add_node(type_node(row.action), kind="type", action=row.action)
        graph.add_node(assessment_node(row.assessment_id), kind="assessment",
                       assessment_id=row.assessment_id, course_id=row.course_id,
                       due_day=row.due_day, module=row.module)
        graph.add_edge(type_node(row.action), assessment_node(row.assessment_id),
                       weight=row.lift, style=row.style, ci_low=row.ci_low,
                       ci_high=row.ci_high)
    return graph


def keystone(graph: nx.Graph) -> str | None:
    """The type with the highest weighted degree over solid edges. None if no solid edge."""
    solid = nx.Graph([(u, v, d) for u, v, d in graph.edges(data=True) if d["style"] == SOLID])
    types = [n for n in solid.nodes if graph.nodes[n]["kind"] == "type"]
    if not types:
        return None
    degree = dict(solid.degree(types, weight="weight"))
    return graph.nodes[max(sorted(types), key=degree.get)]["action"]


def strongest_edges(edges: pd.DataFrame) -> pd.DataFrame:
    """Per assessment: the solid edge with the highest lift, else the best dashed edge."""
    order = edges.assign(_solid=edges["style"] == SOLID).sort_values(
        ["assessment_id", "_solid", "lift"], ascending=[True, False, False])
    return order.drop_duplicates("assessment_id").drop(columns="_solid").reset_index(drop=True)


def assessment_labels(edges: pd.DataFrame) -> pd.DataFrame:
    """One row per assessment with its number inside the presentation (by due day)."""
    rows = edges.drop_duplicates("assessment_id")[["course_id", "assessment_id", "due_day"]]
    rows = rows.sort_values(["course_id", "due_day", "assessment_id"])
    rows["number"] = rows.groupby("course_id").cumcount() + 1
    rows["presentation"] = rows["course_id"].str.split("_").str[-1]
    best = strongest_edges(edges).set_index("assessment_id")
    lift = rows["assessment_id"].map(best["lift"])
    unclear = np.where(rows["assessment_id"].map(best["style"]) == DASHED, " (not clear)", "")
    rows["text"] = [f"#{n} {a} {v:+.0%}{u}" for n, a, v, u in zip(
        rows["number"], rows["assessment_id"].map(best["action"]), lift, unclear, strict=True)]
    return rows


def rescue_note(meta: dict) -> str:
    """Figure caption with the shuffle check, so a reader can judge the solid edges."""
    return (
        "Solid line: 95% range of the lift above 0. Dashed line: positive lift, range "
        "includes 0.<br>Train students after a low score, compared with students of the same "
        "window effort.<br>Shuffle check: "
        f"{meta['null_share_at_least_observed']:.0%} of {meta['null_runs']} shuffled runs give "
        f"{meta['solid_edges']} or more solid edges in all modules, so the solid edges can be "
        "chance.")


def rescue_figure(edges: pd.DataFrame, module: str, note: str) -> go.Figure:
    """Assessments on a due-day timeline, one row per presentation. Types in a left column."""
    edges = edges[edges["module"] == module]
    found = keystone(build_graph(edges))
    labels = assessment_labels(edges)
    presentations = sorted(labels["presentation"].unique())
    types = sorted(edges["action"].unique())
    type_y = {a: i for i, a in enumerate(types)}
    row_y = {p: len(types) + 1 + i for i, p in enumerate(presentations)}
    span = max(labels["due_day"].max() - labels["due_day"].min(), WEEK_DAYS)
    left = labels["due_day"].min() - 0.35 * span
    where = labels.set_index("assessment_id")
    n_lines = sum(-(-n // STRONGEST_PER_LINE) for n in labels.groupby("presentation").size())

    fig = go.Figure()
    for row in edges.sort_values("style").itertuples():
        a = where.loc[row.assessment_id]
        solid = row.style == SOLID
        fig.add_trace(go.Scatter(
            x=[left, a["due_day"]], y=[type_y[row.action], row_y[a["presentation"]]],
            mode="lines", hoverinfo="text", showlegend=False,
            line={"color": BLUE if solid else MUTED, "dash": "solid" if solid else "dash",
                  "width": 1 + 12 * row.lift},
            text=f"{row.action} to {row.course_id} assessment {a['number']}: lift "
                 f"{row.lift:+.0%} (range {row.ci_low:+.0%} to {row.ci_high:+.0%})"))
    fig.add_trace(go.Scatter(
        x=labels["due_day"], y=labels["presentation"].map(row_y), mode="markers+text",
        marker={"size": 11, "color": TEXT}, text=[f"#{n}" for n in labels["number"]],
        # Alternate the label side, because two assessments can share a due day.
        textposition=["top center" if n % 2 else "bottom center" for n in labels["number"]],
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=[left] * len(types), y=list(type_y.values()), mode="markers+text",
        marker={"size": 11, "color": BLUE},
        text=[f"<b>{a} (keystone)</b>" if a == found else a for a in types],
        textposition="middle left", hoverinfo="skip", showlegend=False))
    for p, y in row_y.items():
        fig.add_annotation(x=labels["due_day"].max() + 0.06 * span, y=y, text=p,
                           showarrow=False, xanchor="left", font={"color": TEXT_SECONDARY})
    fig.update_layout(
        title={"text": f"Rescue map, {module}: activity after a low score", "x": 0.01},
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font={"color": TEXT},
        height=340 + 16 * n_lines + 50 * (len(types) + len(presentations)), width=980,
        margin={"l": 40, "r": 40, "t": 60, "b": 230 + 16 * n_lines},
        xaxis={"title": "due day of the assessment (course day)", "gridcolor": GRID,
               "zeroline": False,
               "tickvals": list(range(0, int(labels["due_day"].max()) + 1, 50)),
               "range": [left - 0.32 * span, labels["due_day"].max() + 0.14 * span]},
        yaxis={"visible": False, "range": [-1, max(row_y.values()) + 1]})
    # The strongest edge per assessment, as a list under the chart (labels on the
    # timeline collide when due days are close).
    strongest = ["Strongest edge per assessment:"]
    for p, rows in labels.groupby("presentation"):
        texts = rows["text"].tolist()
        for i in range(0, len(texts), STRONGEST_PER_LINE):
            strongest.append(f"{p}: " + ", ".join(texts[i:i + STRONGEST_PER_LINE]))
    fig.add_annotation(x=0, y=0, yshift=-80, xref="paper", yref="paper", xanchor="left",
                       yanchor="top", showarrow=False, align="left",
                       font={"size": 11, "color": TEXT_SECONDARY},
                       text="<br>".join(strongest) + "<br><br>" + note)
    return fig
