"""Fail if any .py, .md or .yaml file contains an em dash (U+2014)."""

import sys
from pathlib import Path

EM_DASH = chr(0x2014)
SUFFIXES = {".py", ".md", ".yaml", ".yml"}
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}


def files_to_check(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in SUFFIXES
        and not SKIP_DIRS.intersection(p.relative_to(root).parts)
    ]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failures = []
    for path in files_to_check(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                failures.append(f"{path.relative_to(root)}:{number}")
    for failure in failures:
        print(f"em dash: {failure}")
    if failures:
        return 1
    print("em dash check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
