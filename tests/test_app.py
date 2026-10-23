"""AppTest smoke tests, one per tab (BUILD2 Phase F), on synthetic app data in a temp folder,
plus one run on the committed data/app."""

import json
import time
from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from liftpath.adapters.synthetic import write_synthetic
from liftpath.app_data import build_app_data
from liftpath.config import load_config
from liftpath.recover import build_recovery_points
from liftpath.rescue import (
    SOLID,
    null_solid_counts,
    rescue_edges,
    rescue_items,
    strongest_edges,
)
from liftpath.route import item_schedule, projection_tables, score_transitions
from liftpath.sim import run_world
from liftpath.states import build_decision_points, register_canonical, select_candidates

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
APP = str(ROOT / "app" / "streamlit_app.py")
TABS = ["Your route", "Simulator", "Try it", "Rescue map", "Evidence"]
TIMEOUT_S = 180
NULL_RUNS = 5


def write_plan(cfg, con, train, candidates, folder: Path) -> None:
    folder.mkdir()
    transitions = score_transitions(train, candidates, cfg)
    item_schedule(con, cfg).to_parquet(folder / "schedule.parquet", index=False)
    projections, rates = projection_tables(transitions, cfg)
    projections.to_parquet(folder / "projections.parquet", index=False)
    rates.to_parquet(folder / "goal_rates.parquet", index=False)


def write_sim(cfg, folder: Path) -> None:
    folder.mkdir()
    runs = [run_world(w, cfg, cfg.sim_dev_students, cfg.sim_dev_cohorts) for w in cfg.sim_worlds]
    pd.concat([r for r, _ in runs]).to_parquet(folder / "results.parquet", index=False)
    pd.concat([e for _, e in runs]).to_parquet(folder / "estimates.parquet", index=False)


def write_rescue(cfg, con, recovery, candidates, folder: Path) -> None:
    folder.mkdir()
    train = recovery[recovery["split"] == "train"].reset_index(drop=True)
    edges = rescue_edges(train, candidates, cfg)
    null = null_solid_counts(train, candidates, replace(cfg, seed=cfg.seed), NULL_RUNS)
    n_solid = int((edges["style"] == SOLID).sum())
    edges.to_parquet(folder / "edges.parquet", index=False)
    rescue_items(con, train, edges, cfg).to_parquet(folder / "items.parquet", index=False)
    strongest_edges(edges).to_parquet(folder / "strongest.parquet", index=False)
    meta = {"solid_edges": n_solid, "dashed_edges": len(edges) - n_solid,
            "null_runs": NULL_RUNS, "null_mean": float(null.mean()),
            "null_p95": float(np.percentile(null, 95)),
            "null_share_at_least_observed": float((null >= n_solid).mean()), "keystones": {}}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture(scope="module")
def app_dir(tmp_path_factory):
    cfg = load_config(ROOT / "config.yaml")
    work = tmp_path_factory.mktemp("work")
    canonical = work / "canonical"
    write_synthetic(cfg, canonical)
    con = duckdb.connect()
    register_canonical(con, canonical)
    candidates = select_candidates(con, cfg)
    points = build_decision_points(con, cfg, candidates)
    recovery = build_recovery_points(con, cfg, candidates)
    write_plan(cfg, con, points[points["split"] == "train"], candidates, work / "plan")
    write_sim(cfg, work / "sim")
    write_rescue(cfg, con, recovery, candidates, work / "rescue")
    out = tmp_path_factory.mktemp("app")
    sizes = build_app_data(
        cfg, points, candidates, recovery,
        eval_results=json.loads((REPORTS / "eval_results_synthetic.json").read_text("utf-8")),
        fairness=pd.read_json(REPORTS / "fairness_results_synthetic.json"),
        figures={"synthetic_truth.png": REPORTS / "figures" / "synthetic_truth.png"},
        out_dir=out, rescue_dir=work / "rescue", plan_dir=work / "plan", sim_dir=work / "sim")
    for name in ("students.parquet", "plan_projections.parquet", "sim_results.parquet",
                 "rescue_edges.parquet", "effort_cutoffs.parquet"):
        assert name in sizes
    return out


@pytest.fixture
def app(app_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(app_dir))
    monkeypatch.setenv("LIVE_DATA_DIR", str(tmp_path / "live"))
    at = AppTest.from_file(APP, default_timeout=TIMEOUT_S)
    at.run()
    assert not at.exception
    assert [t.label for t in at.tabs] == TABS
    return at


def tab(at: AppTest, name: str):
    found = at.tabs[TABS.index(name)]
    assert len(found.children) > 0
    assert not found.exception
    return found


def texts(element) -> list[str]:
    return [str(e.value) for e in [*element.markdown, *element.caption, *element.subheader]]


def test_route_tab(app):
    tab(app, "Your route")
    app.radio(key="route_effort").set_value("high").run()
    assert not app.exception
    assert any("Effort planned: high" in t for t in texts(tab(app, "Your route")))
    app.radio(key="route_goal").set_value("goal_distinction").run()
    assert not app.exception


def test_simulator_tab(app):
    tab(app, "Simulator")
    app.selectbox(key="sim_world").set_value("hidden_confounder").run()
    assert not app.exception
    found = texts(tab(app, "Simulator"))
    assert any("above the true effect" in t for t in found)


def test_try_it_tab(app, tmp_path):
    found = tab(app, "Try it")
    assert found.info[0].value.startswith("Demo mode. Data resets on restart.")
    app.text_input(key="live_new_id").set_value("s1")
    next(b for b in app.button if b.label == "Add student").click().run()
    app.number_input(key="live_clicks").set_value(25)
    next(b for b in app.button if b.label == "Log activity").click().run()
    app.button(key="live_advise").click().run()
    assert not app.exception
    heads = [s.value for s in tab(app, "Try it").subheader]
    assert heads and heads[0].split(":")[0] in {"Next step", "Explore", "No clear winner",
                                               "Not enough data"}
    assert len(tab(app, "Try it").dataframe) == 1  # the advice log


def test_rescue_tab(app):
    found = tab(app, "Rescue map")
    if found.info:  # no supported edge in this synthetic world
        assert "No rescue edges" in found.info[0].value
    else:
        assert any("shuffle" in t.lower() or "keystone" in t.lower() for t in texts(found))


def test_evidence_tab(app):
    tab(app, "Evidence")
    app.radio(key="evidence_goal").set_value("goal_distinction").run()
    assert not app.exception


def test_committed_app_data(monkeypatch, tmp_path):
    folder = ROOT / "data" / "app"
    if not (folder / "plan_projections.parquet").exists():
        pytest.skip("needs make app-data")
    monkeypatch.setenv("APP_DATA_DIR", str(folder))
    monkeypatch.setenv("LIVE_DATA_DIR", str(tmp_path / "live"))
    at = AppTest.from_file(APP, default_timeout=TIMEOUT_S)
    at.run()
    assert not at.exception
    for name in TABS:
        tab(at, name)
    start = time.time()
    at.run()
    assert not at.exception
    print(f"second run: {time.time() - start:.2f} s")


def test_demo_script_clicks(monkeypatch, tmp_path):
    """The clicks of docs/demo_script.md give the results the script names."""
    folder = ROOT / "data" / "app"
    if not (folder / "plan_projections.parquet").exists():
        pytest.skip("needs make app-data")
    monkeypatch.setenv("APP_DATA_DIR", str(folder))
    monkeypatch.setenv("LIVE_DATA_DIR", str(tmp_path / "live"))
    at = AppTest.from_file(APP, default_timeout=TIMEOUT_S)
    at.run()
    at.selectbox(key="route_module").set_value("GGG").run()
    at.selectbox(key="route_student").set_value("388259 (GGG_2014J)").run()
    at.selectbox(key="route_week").set_value(31).run()
    assert not at.exception
    route = texts(tab(at, "Your route"))
    assert "**First, go back: quizzes** (score 10 on the last assessment)" in route
    assert route[route.index("**Week 31**") + 1] == "course pages"
    assert "Lift +7.6 pp (95% range +0.2 pp to +15.0 pp)." in route
    at.selectbox(key="sim_world").set_value("hidden_confounder").run()
    at.text_input(key="live_new_id").set_value("demo1")
    at.selectbox(key="live_new_module").set_value("GGG")
    next(b for b in at.button if b.label == "Add student").click().run()
    at.selectbox(key="live_week").set_value(3).run()
    at.selectbox(key="live_item_type").set_value("quiz")
    at.number_input(key="live_clicks").set_value(40)
    next(b for b in at.button if b.label == "Log activity").click().run()
    at.button(key="live_advise").click().run()
    assert not at.exception
    assert [s.value for s in tab(at, "Try it").subheader] == ["Next step: discussion forum"]
