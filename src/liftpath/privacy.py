"""Small-count suppression for anything shown or stored in data/app/ (SPEC section 19)."""

import pandas as pd

from liftpath.config import Config


def suppress_counts(df: pd.DataFrame, count_cols: list[str], cfg: Config) -> pd.DataFrame:
    """Set each count below display_min_count to NULL. Flag the row as suppressed."""
    out = df.copy()
    small = out[count_cols].lt(cfg.display_min_count) & out[count_cols].notna()
    for col in count_cols:
        out[col] = out[col].astype("Int64").mask(small[col])
    earlier = out["suppressed"] if "suppressed" in out else False
    out["suppressed"] = small.any(axis=1) | earlier
    return out
