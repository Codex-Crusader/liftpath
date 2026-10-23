"""Rescue map (BUILD2 Phase E): edge rule, graph, keystone and strongest edge."""

from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from liftpath.config import load_config
from liftpath.rescue import (
    DASHED,
    SOLID,
    build_graph,
    keystone,
    rescue_edges,
    strongest_edges,
    type_node,
)

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ["quiz", "forumng", "url"]


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "config.yaml")


def edge(action, assessment_id, lift, style, module="AAA"):
    return {"module": module, "course_id": f"{module}_2014J", "assessment_id": assessment_id,
            "due_day": 10 * assessment_id, "action": action, "lift": lift,
            "ci_low": 0.01 if style == SOLID else -0.05, "ci_high": lift + 0.1,
            "n_did": 40, "n_did_not": 40, "style": style}


@pytest.fixture
def edges():
    return pd.DataFrame([
        edge("quiz", 1, 0.10, SOLID),
        edge("url", 1, 0.05, SOLID), edge("url", 2, 0.04, SOLID),
        # forumng has the most weight, but only from dashed edges.
        edge("forumng", 1, 0.30, DASHED), edge("forumng", 2, 0.30, DASHED),
    ])


def test_graph_builds(edges):
    graph = build_graph(edges)
    assert graph.number_of_nodes() == 3 + 2
    assert graph.number_of_edges() == len(edges)
    assert graph.edges[type_node("quiz"), "assessment:1"]["weight"] == 0.10


def test_keystone_is_max_weighted_degree_over_solid_edges(edges):
    graph = build_graph(edges)
    solid = nx.Graph([(u, v, d) for u, v, d in graph.edges(data=True) if d["style"] == SOLID])
    degree = {n: d for n, d in solid.degree(weight="weight") if n.startswith("type:")}
    assert keystone(graph) == max(degree, key=degree.get).removeprefix("type:") == "quiz"
    assert keystone(build_graph(edges[edges["style"] == DASHED])) is None


def test_strongest_edge_prefers_solid(edges):
    best = strongest_edges(edges).set_index("assessment_id")
    assert best.loc[1, "action"] == "quiz"
    assert best.loc[2, "action"] == "url"


def recovery_points(n_per_arm: int) -> pd.DataFrame:
    """One assessment. Quiz revisits recover more, forum revisits recover less, few url."""
    rng = np.random.default_rng(0)
    n = 2 * n_per_arm
    quiz = np.arange(n) < n_per_arm
    forum = np.arange(n) % 2 == 0
    p = 0.3 + 0.4 * quiz - 0.2 * forum
    return pd.DataFrame({
        "course_id": "AAA_2014J", "module": "AAA", "split": "train", "student_id": np.arange(n),
        "assessment_id": 7, "due_day": 50, "effort_band": "mid",
        "rev_quiz": quiz, "rev_forumng": forum, "rev_url": np.arange(n) < 5,
        "goal_recover": rng.random(n) < p})


def test_edge_rule(cfg):
    out = rescue_edges(recovery_points(200), CANDIDATES, cfg).set_index("action")
    assert out.loc["quiz", "style"] == SOLID
    assert "forumng" not in out.index  # negative lift: no edge
    assert "url" not in out.index  # 5 users is below rescue_min_count: no edge


def test_test_points_are_refused(cfg):
    with pytest.raises(ValueError, match="Test points"):
        rescue_edges(recovery_points(50).assign(split="test"), CANDIDATES, cfg)
