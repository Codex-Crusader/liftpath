"""Smoke test of the Streamlit app on synthetic app data in a temp folder."""

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from liftpath.adapters.synthetic import write_synthetic
from liftpath.app_data import build_app_data
from liftpath.config import load_config
from liftpath.recover import build_recovery_points
from liftpath.states import build_decision_points, register_canonical, select_candidates

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
TAB_COUNT = 5
TIMEOUT_S = 120


@pytest.fixture(scope="module")
def app_dir(tmp_path_factory):
    cfg = load_config(ROOT / "config.yaml")
    canonical = tmp_path_factory.mktemp("canonical")
    write_synthetic(cfg, canonical)
    con = duckdb.connect()
    register_canonical(con, canonical)
    candidates = select_candidates(con, cfg)
    points = build_decision_points(con, cfg, candidates)
    recovery = build_recovery_points(con, cfg, candidates)
    eval_path = REPORTS / "eval_results_synthetic.json"
    fairness_path = REPORTS / "fairness_results_synthetic.json"
    out = tmp_path_factory.mktemp("app")
    sizes = build_app_data(
        cfg, points, candidates, recovery,
        eval_results=json.loads(eval_path.read_text(encoding="utf-8")),
        fairness=pd.read_json(fairness_path),
        figures={"synthetic_truth.png": REPORTS / "figures" / "synthetic_truth.png"},
        out_dir=out)
    assert "students.parquet" in sizes
    return out


def test_app_tabs_run(app_dir, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(app_dir))
    monkeypatch.setenv("LIVE_DATA_DIR", str(app_dir / "no_live"))
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=TIMEOUT_S)
    at.run()
    assert not at.exception
    assert len(at.tabs) == TAB_COUNT
    for tab in at.tabs:
        assert len(tab.children) > 0
        assert not tab.exception


def test_app_other_goal(app_dir, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(app_dir))
    monkeypatch.setenv("LIVE_DATA_DIR", str(app_dir / "no_live"))
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=TIMEOUT_S)
    at.run()
    # Every radio in the app is a goal choice.
    for radio in at.radio:
        radio.set_value("goal_distinction")
    at.run()
    assert not at.exception
