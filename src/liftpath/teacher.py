"""Teacher view logic: the class table, plain-language texts, teacher preferences and the
settings descriptions. The app draws it, so this module has no Streamlit code."""

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from liftpath.config import Config
from liftpath.lift import ABSTAIN, ESTIMATE_COLS, RECOMMEND
from liftpath.recommend import GOAL_TEXT, label, recommend_points
from liftpath.route import rescue_rows

GO_BACK, NO_ACTIVITY, NEXT_STEP, NO_CHANGE = "go_back", "no_activity", "next_step", "no_change"
GROUPS = {GO_BACK: "Go back first", NO_ACTIVITY: "No recent activity",
          NEXT_STEP: "Next step suggested", NO_CHANGE: "No change suggested"}
GROUP_ORDER = list(GROUPS)
TEACHER_GOALS = ("goal_pass", "goal_distinction")
ACTIVITY_WORDS = {"none": "No activity this week", "low": "Less active than most",
                  "mid": "About as active as most", "high": "More active than most"}
NAME_MAX_CHARS = 40
TEMPLATE_MAX_CHARS = 1000
DEFAULT_TEMPLATE = "Hello,\n\n$suggestion\n\nWrite to me if you need help.\n\nBest regards"
KEEP_TEXT = "No activity clearly helps more for students in this position. Keep the current plan."
ABSTAIN_TEXT = "Too few similar past students to suggest a step."
STUDENT_KEEP = "Keep going with your current plan."
SORT_NOTE = ("Sorted by facts from the course log: a low mark on the last assessment first, "
             "then weeks without activity. LiftPath does not predict results.")


@dataclass(frozen=True)
class Prefs:
    """Teacher preferences. They change only what the teacher view shows."""
    course: str | None
    goal: str
    inactive_weeks: int
    show_numbers: bool
    activity_names: dict[str, str] = field(default_factory=dict)
    message_template: str = DEFAULT_TEMPLATE


def default_prefs(cfg: Config) -> Prefs:
    return Prefs(course=None, goal=TEACHER_GOALS[0], inactive_weeks=cfg.teacher_inactive_weeks,
                 show_numbers=False)


def prefs_path(cfg: Config, folder: Path) -> Path:
    return folder / Path(cfg.teacher_settings_path).name


def clean_prefs(raw: object, cfg: Config) -> tuple[Prefs, list[str]]:
    """Preferences from untrusted JSON. Bad values fall back to the defaults, with a note."""
    prefs, notes = default_prefs(cfg), []
    if not isinstance(raw, dict):
        return prefs, ["The settings file is not valid. The defaults are used."]
    checks = {
        "course": lambda v: v is None or isinstance(v, str),
        "goal": lambda v: v in TEACHER_GOALS,
        "inactive_weeks": lambda v: (isinstance(v, int) and not isinstance(v, bool)
                                     and 1 <= v <= cfg.teacher_inactive_weeks_max),
        "show_numbers": lambda v: isinstance(v, bool),
        "message_template": lambda v: isinstance(v, str) and 0 < len(v) <= TEMPLATE_MAX_CHARS,
    }
    values = {}
    for key, ok in checks.items():
        if key not in raw:
            continue
        if ok(raw[key]):
            values[key] = raw[key]
        else:
            notes.append(f"The saved value for '{key}' is not valid. The default is used.")
    names = raw.get("activity_names", {})
    if isinstance(names, dict):
        values["activity_names"] = {
            k: v.strip() for k, v in names.items()
            if isinstance(k, str) and isinstance(v, str) and 0 < len(v.strip()) <= NAME_MAX_CHARS}
    return replace(prefs, **values), notes


def load_prefs(path: Path, cfg: Config) -> tuple[Prefs, list[str]]:
    if not path.exists():
        return default_prefs(cfg), []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_prefs(cfg), ["The settings file is not valid. The defaults are used."]
    return clean_prefs(raw, cfg)


def save_prefs(path: Path, prefs: Prefs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(prefs), indent=2) + "\n", encoding="utf-8")


def activity_name(action, prefs: Prefs) -> str:
    return prefs.activity_names.get(action) or label(action)


def course_label(course_id: str) -> str:
    module, _, presentation = course_id.partition("_")
    return f"{module} ({presentation})" if presentation else course_id


def mark_words(band: pd.Series, cfg: Config) -> pd.Series:
    return band.map({"none": "No marks yet",
                     "low": f"Average mark below {cfg.score_low_max}",
                     "mid": f"Average mark {cfg.score_low_max} to {cfg.score_mid_max - 1}",
                     "high": f"Average mark {cfg.score_mid_max} or more"})


def inactive_weeks(course_rows: pd.DataFrame, week: int) -> pd.Series:
    """Weeks without clicks up to and including week, per student. Uses weeks <= week only."""
    past = course_rows[course_rows["week"] <= week]
    first = past.groupby("student_id")["week"].min()
    active = past[past["effort_band"] != "none"].groupby("student_id")["week"].max()
    last_active = active.reindex(first.index).fillna(first - 1)
    return (week - last_active).astype(int)


def percent(values: pd.Series) -> pd.Series:
    return ((100 * values).round().astype("Int64").astype(str) + "%").astype(object)


def names(actions: pd.Series, prefs: Prefs) -> pd.Series:
    """Activity names as plain strings. An empty action gives an empty string."""
    return actions.map(lambda a: activity_name(a, prefs) if isinstance(a, str) else "").astype(
        object)


def class_table(students: pd.DataFrame, recovery: pd.DataFrame,
                tables: dict[int, pd.DataFrame], course_id: str, week: int, goal: str,
                cfg: Config, prefs: Prefs) -> pd.DataFrame:
    """One row per student registered in the course at the week, in the teacher's order.

    The status comes from recommend_points on the given tables, the same rule and tables as
    the route. The "go back first" flag uses rescue_rows, the same rule as the rescue card.
    """
    course = students[students["course_id"] == course_id]
    now = course[course["week"] == week].reset_index(drop=True)
    now["inactive_weeks"] = now["student_id"].map(inactive_weeks(course, week))
    rec = recommend_points(now, goal, tables, cfg)
    now = now.assign(**{c: rec[c].to_numpy() for c in ["status", "action", "level",
                                                         *ESTIMATE_COLS]})
    back = rescue_rows(now, recovery, cfg)[
        ["student_id", "action", "score", "assessment_id", "low_band", *ESTIMATE_COLS]]
    now = now.merge(back.add_prefix("back_").rename(columns={"back_student_id": "student_id"}),
                    on="student_id", how="left")

    has_back = now["back_action"].notna()
    idle = now["inactive_weeks"] >= prefs.inactive_weeks
    is_rec = now["status"] == RECOMMEND
    now["group"] = np.select([has_back, idle, is_rec], [GO_BACK, NO_ACTIVITY, NEXT_STEP],
                             NO_CHANGE)
    now["group_label"] = now["group"].map(GROUPS)
    # The usual advice: the activity that similar students used most (user_cf, BUILD2 Phase C).
    usual = now[f"{goal}_user_cf_action"]
    now["usual_action"] = usual
    now["usual_name"] = names(usual, prefs)
    now["usual_lift"] = now[f"{goal}_user_cf_lift"]
    now["usual_ci_low"] = now[f"{goal}_user_cf_ci_low"]
    now["usual_ci_high"] = now[f"{goal}_user_cf_ci_high"]
    now["differs"] = is_rec & usual.notna() & (usual != now["action"])
    now["mark"] = mark_words(now["score_band"], cfg)
    now["activity"] = now["effort_band"].map(ACTIVITY_WORDS)

    name_next = names(now["action"], prefs)
    name_back = names(now["back_action"], prefs)
    back_text = "Go back to the earlier " + name_back + " before the next assessment."
    next_text = "Next week, suggest the " + name_next + "."
    if prefs.show_numbers:
        back_text += (" After a low mark, " + percent(now["back_p1_avg"]) + " of similar "
                      "students who did this passed the next assessment, against "
                      + percent(now["back_p0_avg"]) + " who did not.")
        next_text += (" " + percent(now["p1_avg"]) + " of similar students who did this "
                      "reached " + GOAL_TEXT[goal] + ", against " + percent(now["p0_avg"])
                      + " who did not.")
    other = np.where(now["status"] == ABSTAIN, ABSTAIN_TEXT, KEEP_TEXT)
    advice = np.where(is_rec, next_text, other)
    advice = np.where(has_back, np.where(is_rec, back_text + " " + next_text, back_text),
                      advice)
    contact = ("Contact the student first: no activity for "
               + now["inactive_weeks"].astype(str) + " weeks. ")
    now["suggestion"] = np.where(idle, contact + advice, advice)
    back_short = "Go back to the " + name_back
    now["short"] = np.where(
        has_back, np.where(is_rec, back_short + ", then the " + name_next, back_short),
        np.where(is_rec, "Next week: the " + name_next.fillna(""),
                 np.where(now["status"] == ABSTAIN, "Not enough data", "No change")))

    student_back = ("Before the next assessment, go back to the earlier " + name_back
                    + ". Past students in a similar position who did this did better on the "
                      "next assessment.")
    student_next = ("Next week, spend some time on the " + name_next + ". Past students in a "
                    "similar position who did this did better.")
    student = np.where(is_rec, student_next, STUDENT_KEEP)
    student = np.where(has_back, np.where(is_rec, student_back + " After that, also look at the "
                                          + name_next + ".", student_back), student)
    template = Template(prefs.message_template)
    now["message"] = [template.safe_substitute(suggestion=s, student=str(i))
                      for s, i in zip(student, now["student_id"], strict=True)]

    now["_order"] = now["group"].map({g: i for i, g in enumerate(GROUP_ORDER)})
    now = now.sort_values(["_order", "inactive_weeks", "back_score", "student_id"],
                          ascending=[True, False, True, True], na_position="last")
    return now.drop(columns="_order").reset_index(drop=True)


def class_summary(table: pd.DataFrame) -> dict:
    counts = table["group"].value_counts().reindex(GROUP_ORDER, fill_value=0)
    suggested = table.loc[table["status"] == RECOMMEND, "action"].value_counts()
    return {"counts": {g: int(n) for g, n in counts.items()},
            "n_suggested": int((table["status"] == RECOMMEND).sum()),
            "n_differ": int(table["differs"].sum()),
            "top_action": suggested.index[0] if len(suggested) else None,
            "top_action_n": int(suggested.iloc[0]) if len(suggested) else 0}


def default_course(students: pd.DataFrame, goal: str) -> str:
    """The course with the largest share of clear suggestions, so a demo opens on a full list."""
    share = (students[f"{goal}_status"] == RECOMMEND).groupby(students["course_id"]).mean()
    return str(share.idxmax())


def default_week(students: pd.DataFrame, recovery: pd.DataFrame, course_id: str,
                 cfg: Config) -> int:
    """The week with the most "go back first" students, so a demo opens on a busy week."""
    course = students[students["course_id"] == course_id]
    found = rescue_rows(course, recovery, cfg)
    if found.empty:
        return int(course["week"].median())
    counts = found.groupby("week").size()
    return int(counts.idxmax())


# Settings that need an administrator, config.yaml and a rebuild.
ADMIN_SETTINGS = (
    ("low_score", "Low mark", "A mark below this value counts as a low mark. It decides when "
     "a 'go back first' suggestion can appear.", "Edit config.yaml, run make all, deploy "
     "data/app."),
    ("score_low_max", "Mark band: low", "Average marks below this value show as the low band.",
     "Edit config.yaml, run make all, deploy data/app."),
    ("score_mid_max", "Mark band: mid", "Average marks below this value and at or above the "
     "low band show as the mid band.", "Edit config.yaml, run make all, deploy data/app."),
    ("n_candidates", "Activity types compared", "The number of activity types that LiftPath "
     "compares, the most used first.", "Edit config.yaml, run make all, deploy data/app."),
    ("exclude_types", "Activity types left out", "Activity types that LiftPath never "
     "suggests, for example the course home page.", "Edit config.yaml, run make all, deploy "
     "data/app."),
    ("plan_horizon_weeks", "Weeks in a route", "How many weeks a route plans ahead.",
     "Edit config.yaml, then restart the app."),
    ("data_scope", "Data used", "Which data the build uses: full, sample or synthetic.",
     "Edit config.yaml or set DATA_SCOPE, run make all."),
)
# Settings that the evaluation and the privacy rule depend on.
LOCKED_SETTINGS = (
    ("min_count", "Students needed per group", "Both groups need this many student-weeks "
     "before LiftPath suggests an activity. A lower value gives more suggestions, and more "
     "of them can be chance.", "The evaluation results depend on it. A change needs a new "
     "evaluation (make all) and a review of reports/eval.md."),
    ("prior_strength", "Small-group smoothing", "Pulls the rate of a small group toward the "
     "average rate.", "The evaluation results depend on it."),
    ("z", "Range width", "Sets the 95% range. A suggestion needs a range above zero.",
     "The evaluation results depend on it."),
    ("display_min_count", "Smallest count shown", "Counts below this value are hidden in "
     "the app and in data/app.", "Privacy rule. Never lower it."),
)


def setting_value(value) -> str:
    return ", ".join(map(str, value)) if isinstance(value, list | tuple) else str(value)


def settings_rows(cfg: Config, rows: tuple) -> pd.DataFrame:
    return pd.DataFrame({
        "setting": [name for _, name, _, _ in rows],
        "value": [setting_value(getattr(cfg, key)) for key, _, _, _ in rows],
        "what it does": [what for _, _, what, _ in rows],
        "how to change": [how for _, _, _, how in rows],
        "key in config.yaml": [key for key, _, _, _ in rows],
    })
