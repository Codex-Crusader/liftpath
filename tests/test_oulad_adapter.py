from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from liftpath.adapters.oulad import build_canonical
from liftpath.schema import CANONICAL

FIXTURE = {
    "courses.csv": """code_module,code_presentation,module_presentation_length
AAA,2013J,268
""",
    "assessments.csv": """code_module,code_presentation,id_assessment,assessment_type,date,weight
AAA,2013J,1752,TMA,19,10.0
AAA,2013J,1757,Exam,?,100.0
""",
    "vle.csv": """id_site,code_module,code_presentation,activity_type,week_from,week_to
546614,AAA,2013J,homepage,?,?
546943,AAA,2013J,resource,1,2
""",
    "studentInfo.csv": """code_module,code_presentation,id_student,gender,region,\
highest_education,imd_band,age_band,num_of_prev_attempts,studied_credits,disability,final_result
AAA,2013J,11391,M,East Anglian Region,HE Qualification,90-100%,55<=,0,240,N,Pass
AAA,2013J,28400,F,Scotland,HE Qualification,?,35-55,0,60,N,Withdrawn
AAA,2013J,30268,F,North Western Region,A Level or Equivalent,"30-40%",0-35,0,60,Y,Distinction
""",
    "studentRegistration.csv": """code_module,code_presentation,id_student,\
date_registration,date_unregistration
AAA,2013J,11391,-159,?
AAA,2013J,28400,,12
AAA,2013J,30268,-92,?
""",
    "studentAssessment.csv": """id_assessment,id_student,date_submitted,is_banked,score
1752,11391,18,0,78
1752,28400,22,1,?
1752,30268,17,0,85
""",
    "studentVle.csv": """code_module,code_presentation,id_student,id_site,date,sum_click
AAA,2013J,28400,546614,-10,4
AAA,2013J,28400,546943,3,1
AAA,2013J,30268,546614,0,2
""",
}

ARROW_TYPES = {"VARCHAR": pa.string(), "BIGINT": pa.int64(), "DOUBLE": pa.float64(),
               "BOOLEAN": pa.bool_()}


def write_fixture(folder: Path, files: dict[str, str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")


@pytest.fixture
def canonical(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "canonical"
    write_fixture(raw, FIXTURE)
    stats = build_canonical(duckdb.connect(), raw, out)
    tables = {t: pq.read_table(out / f"{t}.parquet").to_pandas() for t in CANONICAL}
    return out, stats, tables


def test_row_counts_and_course_id(canonical):
    _, stats, tables = canonical
    assert {t: stats[t] for t in CANONICAL} == {
        "courses": 1, "enrollments": 3, "items": 2, "events": 3, "assessments": 2,
        "submissions": 3,
    }
    for df in tables.values():
        assert set(df["course_id"]) == {"AAA_2013J"}


def test_schema_matches_canonical(canonical):
    out, _, _ = canonical
    for table, columns in CANONICAL.items():
        schema = pq.read_schema(out / f"{table}.parquet")
        assert schema.names == list(columns)
        for col, kind in columns.items():
            assert schema.field(col).type == ARROW_TYPES[kind], (table, col)


def test_nulls_and_values(canonical):
    _, stats, tables = canonical
    enr = tables["enrollments"].set_index("student_id")
    assert pd.isna(enr.loc[11391, "unreg_day"])
    assert enr.loc[28400, "unreg_day"] == 12
    assert pd.isna(enr.loc[28400, "reg_day"])
    assert pd.isna(enr.loc[28400, "imd_band"])
    assert enr.loc[30268, "imd_band"] == "30-40%"

    sub = tables["submissions"].set_index("student_id")
    assert pd.isna(sub.loc[28400, "score"])
    assert bool(sub.loc[28400, "banked"]) is True
    assert bool(sub.loc[11391, "banked"]) is False

    exam = tables["assessments"].set_index("kind").loc["Exam"]
    assert exam["due_day"] == 268
    assert stats["exam_due_filled"] == 1

    items = tables["items"].set_index("item_type")
    assert pd.isna(items.loc["homepage", "week_from"])
    assert tables["events"]["day"].min() == -10


def test_header_mismatch_raises(tmp_path):
    broken = dict(FIXTURE)
    broken["courses.csv"] = "code_module,code_presentation,length\nAAA,2013J,268\n"
    write_fixture(tmp_path / "raw", broken)
    with pytest.raises(ValueError, match="header"):
        build_canonical(duckdb.connect(), tmp_path / "raw", tmp_path / "canonical")

