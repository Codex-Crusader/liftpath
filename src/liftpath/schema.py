"""Canonical tables (SPEC section 3). Every adapter writes exactly these columns and types."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

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


ARROW_TYPES = {"VARCHAR": pa.string(), "BIGINT": pa.int64(), "DOUBLE": pa.float64(),
               "BOOLEAN": pa.bool_()}


def arrow_schema(table: str) -> pa.Schema:
    return pa.schema([(col, ARROW_TYPES[kind]) for col, kind in CANONICAL[table].items()])


def write_frames(frames: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """Write DataFrames as canonical Parquet tables with exactly the canonical schema."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, columns in CANONICAL.items():
        data = pa.Table.from_pandas(frames[table][list(columns)], schema=arrow_schema(table),
                                    preserve_index=False)
        pq.write_table(data, out_dir / f"{table}.parquet")
