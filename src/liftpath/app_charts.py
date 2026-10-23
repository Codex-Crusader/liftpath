"""Plotly charts for the app (BUILD2 Phase F). Colors come from style.py."""

import pandas as pd
import plotly.graph_objects as go

from liftpath.figures import POLICY_NAMES
from liftpath.route import PROJECTION_NOTE, Route
from liftpath.style import BLUE, GRID, METHOD_COLORS, MUTED, SURFACE, TEXT, TEXT_SECONDARY

WORLD_NAMES = {"standard": "standard world", "hidden_confounder": "hidden confounder world"}
KIND_NAMES = {"observational": "LiftPath lift (observational)",
              "experimental": "explore effect (experimental)"}
KIND_COLORS = {"observational": METHOD_COLORS["liftpath"],
               "experimental": METHOD_COLORS["liftpath_explore"]}
KIND_SHIFT = {"observational": -0.1, "experimental": 0.1}


def base_layout(fig: go.Figure, title: str, height: int) -> go.Figure:
    fig.update_layout(title={"text": title, "x": 0.01}, height=height, paper_bgcolor=SURFACE,
                      plot_bgcolor=SURFACE, font={"color": TEXT},
                      margin={"l": 10, "r": 10, "t": 50, "b": 40})
    fig.update_xaxes(gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID)
    return fig


def projection_chart(route: Route, goal_name: str) -> go.Figure:
    """Projected goal rate for the route and for the typical path, from 0."""
    values = [route.projected_route, route.projected_typical]
    fig = go.Figure(go.Bar(
        x=[100 * v for v in values], y=["Your route", "Typical path"], orientation="h",
        marker_color=[BLUE, MUTED], text=[f"{v:.1%}" for v in values], textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    fig.update_xaxes(range=[0, 105], ticksuffix="%")
    return base_layout(fig, f"Projected chance of {goal_name}. {PROJECTION_NOTE}", 200)


def sim_pass_rate_chart(results: pd.DataFrame, policies: list[str], last: int,
                        world: str) -> go.Figure:
    """Pass rate per cohort up to cohort last, one line per policy, with end labels."""
    rows = results[results["policy"].isin(policies) & (results["cohort"] <= last)]
    fig = go.Figure()
    for policy, part in rows.groupby("policy", sort=False):
        part = part.sort_values("cohort")
        ours = policy.startswith("liftpath")
        fig.add_trace(go.Scatter(
            x=part["cohort"], y=100 * part["pass_rate"], mode="lines+markers+text",
            name=POLICY_NAMES[policy],
            line={"color": METHOD_COLORS[policy], "width": 3.5 if ours else 2,
                  "dash": "dash" if policy == "none" else "solid"},
            text=[POLICY_NAMES[policy] if c == part["cohort"].max() else ""
                  for c in part["cohort"]],
            textposition="middle right", textfont={"color": TEXT_SECONDARY},
            hovertemplate=f"{POLICY_NAMES[policy]}, cohort %{{x}}: %{{y:.1f}}%<extra></extra>"))
    fig.update_xaxes(title="cohort (cohort 0: no advice for all)", dtick=1,
                     range=[-0.2, max(last, 1) + 1.2])
    fig.update_yaxes(title="pass rate", ticksuffix="%")
    fig.update_layout(showlegend=False)
    return base_layout(fig, f"Pass rate by cohort, {WORLD_NAMES[world]}", 420)


def sim_estimates_chart(estimates: pd.DataFrame, action: str) -> go.Figure:
    """Observational and experimental estimates per cohort, with the true effect line."""
    rows = estimates[estimates["action"] == action]
    truth = rows.groupby("cohort")["true_effect"].first()
    fig = go.Figure(go.Scatter(x=truth.index, y=100 * truth.to_numpy(), mode="lines",
                               name="true effect", line={"color": TEXT, "dash": "dash"}))
    for kind, name in KIND_NAMES.items():
        part = rows[rows["kind"] == kind].sort_values("cohort")
        if part.empty:
            continue
        est, low, high = (100 * part[c] for c in ("estimate", "ci_low", "ci_high"))
        fig.add_trace(go.Scatter(
            x=part["cohort"] + KIND_SHIFT[kind], y=est, mode="markers", name=name,
            marker={"color": KIND_COLORS[kind], "size": 9},
            error_y={"type": "data", "array": high - est, "arrayminus": est - low,
                     "color": KIND_COLORS[kind]},
            hovertemplate=f"{name}, cohort %{{x:.0f}}: %{{y:+.1f}} pp<extra></extra>"))
    fig.add_hline(y=0, line_color=MUTED)
    fig.update_xaxes(title="estimate before the cohort", dtick=1)
    fig.update_yaxes(title="effect on pass", ticksuffix=" pp")
    fig.update_layout(legend={"orientation": "h", "y": -0.25})
    title = "quiz (true effect)" if action == "quiz" else f"{action} (no true effect)"
    return base_layout(fig, title, 380)
