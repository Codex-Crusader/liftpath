"""OULAD raw CSVs to canonical Parquet (SPEC sections 2 and 3)."""

from pathlib import Path

import duckdb

from liftpath.schema import ASSESSMENT_KINDS, CANONICAL, FINAL_RESULTS, typed_select

RAW_COLUMNS: dict[str, list[str]] = {
    "courses": ["code_module", "code_presentation", "module_presentation_length"],
    "assessments": [
        "code_module", "code_presentation", "id_assessment", "assessment_type", "date", "weight",
    ],
    "vle": ["id_site", "code_module", "code_presentation", "activity_type", "week_from", "week_to"],
    "studentInfo": [
        "code_module", "code_presentation", "id_student", "gender", "region",
        "highest_education", "imd_band", "age_band", "num_of_prev_attempts",
        "studied_credits", "disability", "final_result",
    ],
    "studentRegistration": [
        "code_module", "code_presentation", "id_student", "date_registration",
        "date_unregistration",
    ],
    "studentAssessment": ["id_assessment", "id_student", "date_submitted", "is_banked", "score"],
    "studentVle": [
        "code_module", "code_presentation", "id_student", "id_site", "date", "sum_click",
    ],
}

COURSE_ID = "code_module || '_' || code_presentation"

CANONICAL_SQL: dict[str, str] = {
    "courses": f"""
        SELECT {COURSE_ID} AS course_id, code_module AS module,
               code_presentation AS presentation, module_presentation_length AS length_days
        FROM raw_courses""",
    "enrollments": """
        SELECT i.code_module || '_' || i.code_presentation AS course_id,
               i.code_module AS module, i.code_presentation AS presentation,
               i.id_student AS student_id, r.date_registration AS reg_day,
               r.date_unregistration AS unreg_day, i.final_result, i.gender, i.age_band,
               i.imd_band, i.disability, i.region, i.highest_education
        FROM raw_studentInfo i
        LEFT JOIN raw_studentRegistration r
          ON i.code_module = r.code_module
         AND i.code_presentation = r.code_presentation
         AND i.id_student = r.id_student""",
    "items": f"""
        SELECT {COURSE_ID} AS course_id, id_site AS item_id, activity_type AS item_type,
               week_from, week_to
        FROM raw_vle""",
    "events": f"""
        SELECT {COURSE_ID} AS course_id, id_student AS student_id, id_site AS item_id,
               date AS day, sum_click AS clicks
        FROM raw_studentVle""",
    # SPEC section 2: an Exam with no date is due at the end of the course.
    "assessments": """
        SELECT a.code_module || '_' || a.code_presentation AS course_id,
               a.id_assessment AS assessment_id, a.assessment_type AS kind,
               COALESCE(a.date, CASE WHEN a.assessment_type = 'Exam'
                                     THEN c.module_presentation_length END) AS due_day,
               a.weight
        FROM raw_assessments a
        JOIN raw_courses c
          ON a.code_module = c.code_module AND a.code_presentation = c.code_presentation""",
    "submissions": """
        SELECT a.code_module || '_' || a.code_presentation AS course_id,
               s.id_student AS student_id, s.id_assessment AS assessment_id,
               s.date_submitted AS submit_day, s.score,
               CAST(s.is_banked AS INTEGER) = 1 AS banked
        FROM raw_studentAssessment s
        JOIN raw_assessments a ON s.id_assessment = a.id_assessment""",
}

# Each canonical table must keep the row count of its source file.
SOURCE_OF = {
    "courses": "courses",
    "enrollments": "studentInfo",
    "items": "vle",
    "events": "studentVle",
    "assessments": "assessments",
    "submissions": "studentAssessment",
}


def register_raw(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    """Create one view per raw CSV. Every value is text, and '?' or empty is NULL."""
    for name, expected in RAW_COLUMNS.items():
        path = (raw_dir / f"{name}.csv").as_posix()
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW raw_{name} AS SELECT * FROM read_csv("
            f"'{path}', header = true, all_varchar = true, nullstr = ['?', ''])"
        )
        found = [row[0] for row in con.execute(f"DESCRIBE raw_{name}").fetchall()]
        if found != expected:
            raise ValueError(f"{name}.csv header differs from SPEC: {found}")


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


def check_raw(con: duckdb.DuckDBPyConnection) -> None:
    for name in ("studentInfo", "studentRegistration"):
        dupes = scalar(
            con,
            f"SELECT count(*) - count(DISTINCT (code_module, code_presentation, id_student)) "
            f"FROM raw_{name}",
        )
        if dupes:
            raise ValueError(f"{name}.csv has {dupes} duplicate student keys")
    dupes = scalar(con, "SELECT count(*) - count(DISTINCT id_assessment) FROM raw_assessments")
    if dupes:
        raise ValueError(f"assessments.csv has {dupes} duplicate id_assessment values")
    checks = {
        "final_result": ("raw_studentInfo", FINAL_RESULTS),
        "assessment_type": ("raw_assessments", ASSESSMENT_KINDS),
    }
    for col, (view, allowed) in checks.items():
        values = {row[0] for row in con.execute(f"SELECT DISTINCT {col} FROM {view}").fetchall()}
        if not values <= set(allowed):
            raise ValueError(f"unknown {col} values: {sorted(values - set(allowed), key=str)}")


def build_canonical(con: duckdb.DuckDBPyConnection, raw_dir: Path, out_dir: Path) -> dict:
    """Write the six canonical tables. Return row counts and data quality counts."""
    register_raw(con, raw_dir)
    check_raw(con)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {}
    for table in CANONICAL:
        target = (out_dir / f"{table}.parquet").as_posix()
        con.execute(f"COPY ({typed_select(table, CANONICAL_SQL[table])}) TO '{target}' "
                    f"(FORMAT parquet)")
        written = scalar(con, f"SELECT count(*) FROM read_parquet('{target}')")
        source = scalar(con, f"SELECT count(*) FROM raw_{SOURCE_OF[table]}")
        if written != source:
            raise ValueError(f"{table}: wrote {written} rows, source has {source}")
        stats[table] = written
    stats["exam_due_filled"] = scalar(
        con, "SELECT count(*) FROM raw_assessments WHERE assessment_type = 'Exam' AND date IS NULL"
    )
    stats["non_exam_due_null"] = scalar(
        con, "SELECT count(*) FROM raw_assessments WHERE assessment_type <> 'Exam' AND date IS NULL"
    )
    return stats
