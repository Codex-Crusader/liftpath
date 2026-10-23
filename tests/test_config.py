from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from liftpath.config import load_config
from liftpath.paths import canonical_dir, scope_dir

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def test_config_loads(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    cfg = load_config(CONFIG_PATH)
    assert cfg.scope == "full"
    assert cfg.min_count == 30
    assert cfg.exclude_types == ("homepage",)
    assert cfg.z == pytest.approx(1.96)
    with pytest.raises(FrozenInstanceError):
        cfg.min_count = 1


def test_data_scope_override(monkeypatch):
    monkeypatch.setenv("DATA_SCOPE", "sample")
    cfg = load_config(CONFIG_PATH)
    assert cfg.scope == "sample"
    assert cfg.data_scope == "full"
    assert scope_dir(cfg) == Path("data/processed/sample")
    assert canonical_dir(cfg) == Path("data/processed/sample/canonical")


def test_bad_scope_rejected(monkeypatch):
    monkeypatch.setenv("DATA_SCOPE", "everything")
    with pytest.raises(ValueError):
        load_config(CONFIG_PATH)


def test_unknown_key_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    bad = tmp_path / "config.yaml"
    bad.write_text(CONFIG_PATH.read_text(encoding="utf-8") + "extra_key: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad)
