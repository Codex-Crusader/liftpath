"""Lift estimator and back-off levels (SPEC sections 7, 10 and 11)."""

LEVELS: dict[int, list[str]] = {
    0: ["module", "week_block", "score_band", "effort_band"],
    1: ["module", "score_band", "effort_band"],
    2: ["score_band", "effort_band"],
}
