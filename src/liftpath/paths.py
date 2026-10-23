"""Data directory layout. All paths are relative to the repo root."""

from pathlib import Path

from liftpath.config import Config

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
TMP_DIR = DATA_DIR / "tmp"
APP_DIR = DATA_DIR / "app"
REPORTS_DIR = Path("reports")


def scope_dir(cfg: Config) -> Path:
    return PROCESSED_DIR / cfg.scope


def canonical_dir(cfg: Config) -> Path:
    return scope_dir(cfg) / "canonical"
