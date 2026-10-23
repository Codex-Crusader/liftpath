"""Write reports/headline.json and reports/headline.md (BUILD2 Phase G)."""

import json

import pandas as pd

from liftpath.config import load_config
from liftpath.headline import build_headline, headline_markdown
from liftpath.paths import PROCESSED_DIR, REPORTS_DIR


def main() -> int:
    cfg = load_config()
    eval_results = json.loads((REPORTS_DIR / "eval_results.json").read_text(encoding="utf-8"))
    results = pd.read_parquet(PROCESSED_DIR / "synthetic" / "sim" / "results.parquet")
    headline = build_headline(eval_results, results, cfg)
    (REPORTS_DIR / "headline.json").write_text(json.dumps(headline, indent=2) + "\n",
                                               encoding="utf-8")
    (REPORTS_DIR / "headline.md").write_text(headline_markdown(headline), encoding="utf-8")
    print(f"story: {headline['story']}")
    print(headline["headline"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
