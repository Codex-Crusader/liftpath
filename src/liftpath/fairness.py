"""LiftPath results per demographic group (SPEC section 17)."""

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.evaluate import follower_lift
from liftpath.lift import ABSTAIN, STUDENT_KEY

ATTRIBUTES = ["gender", "age_band", "imd_band", "disability"]
# SPEC section 17: a group with fewer than 200 unique students is a small sample.
SMALL_SAMPLE_STUDENTS = 200
UNKNOWN = "unknown"


def subgroup_report(test: pd.DataFrame, actions: pd.Series, goal_col: str,
                    cfg: Config) -> pd.DataFrame:
    """test needs the ATTRIBUTES columns and the LiftPath "status" column. actions holds the
    LiftPath action per point (None when the status is not recommend)."""
    rows = []
    for attribute in ATTRIBUTES:
        groups = test[attribute].fillna(UNKNOWN)
        for group in sorted(groups.unique()):
            mask = (groups == group).to_numpy()
            part = test[mask]
            result = follower_lift(part, actions[mask], goal_col, cfg,
                                   np.random.default_rng(cfg.seed))
            n_students = int(part[STUDENT_KEY].drop_duplicates().shape[0])
            rows.append({
                "attribute": attribute, "group": group, "n_students": n_students,
                "n_points": len(part),
                "coverage": float((part["status"] != ABSTAIN).mean()),
                "recommend_share": result.coverage,
                "lift": result.lift, "ci_low": result.ci_low, "ci_high": result.ci_high,
                "small_sample": n_students < SMALL_SAMPLE_STUDENTS,
            })
    return pd.DataFrame(rows)
