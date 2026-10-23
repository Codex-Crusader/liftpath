"""Show the trap card in the app for 3 sample students with different final results.

BUILD2 Phase C. One student reached distinction, one passed without distinction and one did
not pass. The final result comes from decision_points.parquet and only chooses which students
to show. It never enters data/app or any recommendation. Inside each group the script prefers
a different card case: user_cf agrees with LiftPath, user_cf differs with a range that
contains 0, or user_cf differs with a negative range.
Run with: uv run python scripts/demo_trap.py
"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from liftpath.lift import RECOMMEND, STUDENT_KEY

ROOT = Path(__file__).resolve().parents[1]
GOAL = "goal_pass"
TIMEOUT_S = 300
POINTS = ROOT / "data" / "processed" / "full" / "decision_points.parquet"
RESULTS = ("distinction", "pass", "not pass")
CASES = ("agree", "no clear help", "negative lift")


def final_results() -> pd.DataFrame:
    goals = pd.read_parquet(POINTS, columns=[*STUDENT_KEY, "goal_pass", "goal_distinction"])
    goals = goals.drop_duplicates(STUDENT_KEY)
    result = pd.Series("not pass", index=goals.index)
    result[goals["goal_pass"].astype(bool)] = "pass"
    result[goals["goal_distinction"].astype(bool)] = "distinction"
    return goals[STUDENT_KEY].assign(result=result)


def card_case(rows: pd.DataFrame) -> pd.Series:
    """The card case of each row: agree, no clear help, negative lift or other."""
    other = rows[f"{GOAL}_user_cf_action"]
    differ = other.notna() & (other != rows[f"{GOAL}_action"])
    low, high = rows[f"{GOAL}_user_cf_ci_low"], rows[f"{GOAL}_user_cf_ci_high"]
    case = pd.Series("other", index=rows.index)
    case[other == rows[f"{GOAL}_action"]] = "agree"
    case[differ & (low <= 0) & (high >= 0)] = "no clear help"
    case[differ & (high < 0)] = "negative lift"
    return case


def pick_cases(students: pd.DataFrame, results: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    rec = students[students[f"{GOAL}_status"] == RECOMMEND]
    rec = rec.merge(results, on=STUDENT_KEY).assign(case=lambda d: card_case(d))
    rec = rec.sort_values(["course_id", "student_id", "week"])
    picked = []
    for result, case in zip(RESULTS, CASES, strict=True):
        group = rec[rec["result"] == result]
        rows = group[group["case"] == case]
        row = (rows if len(rows) else group).iloc[0]
        picked.append((result, row["case"], row))
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
    for result, case, row in pick_cases(students, final_results()):
        print(f"== final result {result}, card case {case}: student {row['student_id']} "
              f"({row['course_id']}), week {row['week']}")
        for line in show(row):
            print(line)


if __name__ == "__main__":
    main()
