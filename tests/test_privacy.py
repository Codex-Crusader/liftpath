from pathlib import Path

import pandas as pd

from liftpath.config import load_config
from liftpath.privacy import suppress_counts

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def test_counts_below_five_are_suppressed(monkeypatch):
    monkeypatch.delenv("DATA_SCOPE", raising=False)
    cfg = load_config(CONFIG_PATH)
    df = pd.DataFrame({"cell": ["a", "b", "c", "d"], "n1": [4, 5, 0, 30],
                       "n0": [10, 3, 7, None]})
    out = suppress_counts(df, ["n1", "n0"], cfg)
    assert out["n1"].isna().tolist() == [True, False, True, False]
    assert out["n0"].isna().tolist() == [False, True, False, True]
    assert out["suppressed"].tolist() == [True, True, True, False]
    assert out.loc[1, "n1"] == 5
    assert df["n1"].tolist() == [4, 5, 0, 30]

    again = suppress_counts(out.assign(n2=[9, 9, 9, 9]), ["n2"], cfg)
    assert again["suppressed"].tolist() == [True, True, True, False]
