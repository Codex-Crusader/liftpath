"""Canonical tables (SPEC section 3). Every adapter writes exactly these columns and types."""

CANONICAL: dict[str, dict[str, str]] = {
    "courses": {
        "course_id": "VARCHAR",
        "module": "VARCHAR",
        "presentation": "VARCHAR",
        "length_days": "BIGINT",
    },
    "enrollments": {
        "course_id": "VARCHAR",
        "module": "VARCHAR",
        "presentation": "VARCHAR",
        "student_id": "BIGINT",
        "reg_day": "BIGINT",
        "unreg_day": "BIGINT",
        "final_result": "VARCHAR",
        "gender": "VARCHAR",
        "age_band": "VARCHAR",
        "imd_band": "VARCHAR",
        "disability": "VARCHAR",
        "region": "VARCHAR",
        "highest_education": "VARCHAR",
    },
    "items": {
        "course_id": "VARCHAR",
        "item_id": "BIGINT",
        "item_type": "VARCHAR",
        "week_from": "BIGINT",
        "week_to": "BIGINT",
    },
    "events": {
        "course_id": "VARCHAR",
        "student_id": "BIGINT",
        "item_id": "BIGINT",
        "day": "BIGINT",
        "clicks": "BIGINT",
    },
    "assessments": {
        "course_id": "VARCHAR",
        "assessment_id": "BIGINT",
        "kind": "VARCHAR",
        "due_day": "BIGINT",
        "weight": "DOUBLE",
    },
    "submissions": {
        "course_id": "VARCHAR",
        "student_id": "BIGINT",
        "assessment_id": "BIGINT",
        "submit_day": "BIGINT",
        "score": "DOUBLE",
        "banked": "BOOLEAN",
    },
}

FINAL_RESULTS = ("Pass", "Distinction", "Fail", "Withdrawn")
ASSESSMENT_KINDS = ("TMA", "CMA", "Exam")


def typed_select(table: str, inner_sql: str) -> str:
    """Wrap a query so it returns exactly the canonical columns, cast to canonical types."""
    casts = ", ".join(f"CAST({col} AS {kind}) AS {col}" for col, kind in CANONICAL[table].items())
    return f"SELECT {casts} FROM ({inner_sql})"
