"""Command line entry point: python -m liftpath.cli <step>."""

import argparse
import runpy
from dataclasses import replace
from pathlib import Path

from liftpath.adapters.oulad import build_canonical
from liftpath.config import Config, load_config
from liftpath.db import connect
from liftpath.paths import RAW_DIR, canonical_dir
from liftpath.scopes import build_sample

SCRIPTS_DIR = Path("scripts")

STEPS = (
    "data",
    "sample",
    "synthetic",
    "profile",
    "states",
    "lifts",
    "recover",
    "eval",
    "app-data",
)


def run_script(name: str) -> None:
    code = runpy.run_path(str(SCRIPTS_DIR / name))["main"]()
    if code:
        raise SystemExit(code)


def step_data(cfg: Config) -> None:
    run_script("download_oulad.py")
    full = replace(cfg, scope="full")
    stats = build_canonical(connect(full), RAW_DIR, canonical_dir(full))
    for key, value in stats.items():
        print(f"{key}: {value:,}")


def step_sample(cfg: Config) -> None:
    stats = build_sample(connect(cfg), cfg)
    for key, value in stats.items():
        print(f"{key}: {value}")


def step_profile(cfg: Config) -> None:
    run_script("profile_data.py")


def not_built(cfg: Config) -> None:
    print("not built yet")


HANDLERS = {"data": step_data, "sample": step_sample, "profile": step_profile}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="liftpath")
    sub = parser.add_subparsers(dest="step", required=True)
    for step in STEPS:
        sub.add_parser(step)
    args = parser.parse_args(argv)
    HANDLERS.get(args.step, not_built)(load_config())


if __name__ == "__main__":
    main()
