"""Command line entry point: python -m liftpath.cli <step>."""

import argparse

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


def not_built(step: str) -> None:
    print(f"{step}: not built yet")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="liftpath")
    sub = parser.add_subparsers(dest="step", required=True)
    for step in STEPS:
        sub.add_parser(step)
    args = parser.parse_args(argv)
    not_built(args.step)


if __name__ == "__main__":
    main()
