"""Synthetic data with a known truth (SPEC section 16). Writes the canonical tables.

quiz has a true effect on the outcome. forumng has none, but its use rises with effort,
so a method without effort control rates it too high.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.schema import write_frames

WEEK_DAYS = 7
# The only action with a true effect on the outcome (outcome_quiz_effect).
TRUE_EFFECT_ACTIONS = ("quiz",)


@dataclass(frozen=True)
class Engagement:
    a: float
    b: float


@dataclass(frozen=True)
class SyntheticParams:
    module: str = "SYN"
    presentations: tuple[str, ...] = ("2013J", "2014J")
    length_days: int = 84
    click_base: float = 1.8
    click_ability: float = 0.7
    click_noise_sd: float = 0.3
    engagement: dict[str, Engagement] = field(default_factory=lambda: {
        "oucontent": Engagement(-1.5, 0.5),
        "quiz": Engagement(-0.4, 0.0),
        "forumng": Engagement(-5.0, 2.0),
        "resource": Engagement(-1.5, 0.5),
        "url": Engagement(-1.5, 0.5),
        "subpage": Engagement(-1.5, 0.5),
        "ouwiki": Engagement(-1.5, 0.5),
        "glossary": Engagement(-1.5, 0.5),
        "homepage": Engagement(2.0, 0.0),
    })
    tma_due: tuple[int, ...] = (30, 65)
    tma_weight: float = 50.0
    exam_weight: float = 100.0
    score_base: float = 55.0
    score_ability: float = 15.0
    score_per_quiz_week: float = 3.0
    score_noise_sd: float = 10.0
    score_max: float = 100.0
    outcome_base: float = 0.2
    outcome_ability: float = 1.5
    outcome_quiz_effect: float = 0.35
    outcome_quiz_center: float = 4.8
    distinction_logit: float = 2.0
    withdraw_share: float = 0.10
    withdraw_first_week: int = 2
    withdraw_last_week: int = 10
    reg_day: int = -10


DEMOGRAPHICS = {
    "gender": ["F", "M"],
    "age_band": ["0-35", "35-55", "55<="],
    "imd_band": ["0-10%", "10-20", "20-30%", "30-40%", "40-50%", "50-60%", "60-70%",
                 "70-80%", "80-90%", "90-100%"],
    "disability": ["N", "Y"],
    "region": ["East Anglian Region", "Scotland", "London Region", "Wales"],
    "highest_education": ["A Level or Equivalent", "HE Qualification",
                          "Lower Than A Level"],
}


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def presentation_frames(rng: np.random.Generator, p: SyntheticParams, presentation: str,
                        n_students: int, first_id: int) -> dict[str, pd.DataFrame]:
    course_id = f"{p.module}_{presentation}"
    n_weeks = int(np.ceil(p.length_days / WEEK_DAYS))
    types = list(p.engagement)
    ids = np.arange(first_id, first_id + n_students)
    u = rng.normal(0, 1, n_students)

    withdraws = rng.random(n_students) < p.withdraw_share
    withdraw_week = rng.integers(p.withdraw_first_week, p.withdraw_last_week + 1, n_students)
    weeks = np.arange(n_weeks)
    active = ~withdraws[:, None] | (weeks[None, :] <= withdraw_week[:, None])

    noise = rng.normal(0, p.click_noise_sd, (n_students, n_weeks))
    total = rng.poisson(np.exp(p.click_base + p.click_ability * u[:, None] + noise)) * active
    engaged = np.stack([
        (rng.random((n_students, n_weeks))
         < sigmoid(e.a + e.b * np.log1p(total))) & (total > 0)
        for e in p.engagement.values()
    ], axis=2)
    n_engaged = engaged.sum(axis=2)
    per_type = np.maximum(1, total // np.maximum(n_engaged, 1))

    s_idx, w_idx, t_idx = np.nonzero(engaged)
    events = pd.DataFrame({
        "course_id": course_id,
        "student_id": ids[s_idx],
        "item_id": t_idx + 1,
        "day": WEEK_DAYS * w_idx + rng.integers(0, WEEK_DAYS, len(s_idx)),
        "clicks": per_type[s_idx, w_idx],
    })

    quiz = engaged[:, :, types.index("quiz")]
    week_end = WEEK_DAYS * weeks + WEEK_DAYS - 1
    sub_rows = []
    for k, due in enumerate(p.tma_due):
        q = quiz[:, week_end < due].sum(axis=1)
        raw = (p.score_base + p.score_ability * u + p.score_per_quiz_week * q
               + rng.normal(0, p.score_noise_sd, n_students))
        score = np.clip(np.round(raw), 0, p.score_max)
        submitted = ~withdraws | (WEEK_DAYS * withdraw_week + WEEK_DAYS - 1 >= due)
        sub_rows.append(pd.DataFrame({
            "course_id": course_id, "student_id": ids[submitted], "assessment_id": k + 1,
            "submit_day": due, "score": score[submitted], "banked": False,
        }))

    logit = (p.outcome_base + p.outcome_ability * u
             + p.outcome_quiz_effect * (quiz.sum(axis=1) - p.outcome_quiz_center))
    passed = rng.random(n_students) < sigmoid(logit)
    result = np.where(passed, np.where(logit > p.distinction_logit, "Distinction", "Pass"), "Fail")
    result = np.where(withdraws, "Withdrawn", result)

    enrollments = pd.DataFrame({
        "course_id": course_id, "module": p.module, "presentation": presentation,
        "student_id": ids, "reg_day": p.reg_day,
        "unreg_day": pd.array(np.where(withdraws, week_end[withdraw_week], -1), dtype="Int64"),
        "final_result": result,
    })
    enrollments.loc[~withdraws, "unreg_day"] = pd.NA
    for col, values in DEMOGRAPHICS.items():
        enrollments[col] = rng.choice(values, n_students)

    assessments = pd.DataFrame({
        "course_id": course_id,
        "assessment_id": np.arange(1, len(p.tma_due) + 2),
        "kind": ["TMA"] * len(p.tma_due) + ["Exam"],
        "due_day": [*p.tma_due, p.length_days],
        "weight": [p.tma_weight] * len(p.tma_due) + [p.exam_weight],
    })
    items = pd.DataFrame({"course_id": course_id, "item_id": np.arange(1, len(types) + 1),
                          "item_type": types, "week_from": pd.NA, "week_to": pd.NA})
    courses = pd.DataFrame({"course_id": [course_id], "module": [p.module],
                            "presentation": [presentation], "length_days": [p.length_days]})
    return {"courses": courses, "enrollments": enrollments, "items": items, "events": events,
            "assessments": assessments, "submissions": pd.concat(sub_rows, ignore_index=True)}


def generate(cfg: Config, params: SyntheticParams | None = None) -> dict[str, pd.DataFrame]:
    p = params or SyntheticParams()
    rng = np.random.default_rng(cfg.seed)
    n = cfg.synthetic_students_per_presentation
    parts = [presentation_frames(rng, p, pres, n, first_id=1 + i * n)
             for i, pres in enumerate(p.presentations)]
    return {table: pd.concat([part[table] for part in parts], ignore_index=True)
            for table in parts[0]}


def write_synthetic(cfg: Config, out_dir: Path, params: SyntheticParams | None = None) -> dict:
    frames = generate(cfg, params)
    write_frames(frames, out_dir)
    return {table: len(df) for table, df in frames.items()}
