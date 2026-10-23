"""Show the trap card in the app for 3 sample students with different card outcomes.

BUILD2 Phase C. The cases: user_cf agrees with LiftPath, user_cf differs and its range
contains 0, and user_cf differs with a negative range.
Run with: uv run python scripts/demo_trap.py
"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from liftpath.lift import RECOMMEND

ROOT = Path(__file__).resolve().parents[1]
GOAL = "goal_pass"
TIMEOUT_S = 300


def pick_cases(students: pd.DataFrame) -> dict[str, pd.Series]:
    rec = students[students[f"{GOAL}_status"] == RECOMMEND]
    other = rec[f"{GOAL}_user_cf_action"]
    differ = rec[other.notna() & (other != rec[f"{GOAL}_action"])]
    low, high = differ[f"{GOAL}_user_cf_ci_low"], differ[f"{GOAL}_user_cf_ci_high"]
    cases = {"agree": rec[other == rec[f"{GOAL}_action"]],
             "no clear help": differ[(low <= 0) & (high >= 0)],
             "negative lift": differ[high < 0]}
    picked, used = {}, set()
    for name, rows in cases.items():
        rows = rows.sort_values(["course_id", "student_id", "week"])
        row = rows[~rows["student_id"].isin(used)].iloc[0]
        used.add(row["student_id"])
        picked[name] = row
    return picked


def show(row: pd.Series) -> list[str]:
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=TIMEOUT_S)
    at.run()
    at.selectbox[0].set_value(row["module"]).run()
    at.selectbox[1].set_value(f"{row['student_id']} ({row['course_id']})").run()
    at.selectbox[2].set_value(row["week"]).run()
    assert not at.exception
    tab = at.tabs[0]
    texts = [m.value for m in tab.subheader] + [m.value for m in tab.markdown]
    start = texts.index("**What common advice says**")
    return [texts[0], *texts[start + 1:]]


def main() -> None:
    students = pd.read_parquet(ROOT / "data" / "app" / "students.parquet")
    for name, row in pick_cases(students).items():
        print(f"== {name}: student {row['student_id']} ({row['course_id']}), week {row['week']}")
        for line in show(row):
            print(line)


if __name__ == "__main__":
    main()
