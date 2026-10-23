# LiftPath progress

## Status
| Phase | Name | Status |
|---|---|---|
| 0 | Setup | done |
| 1 | Data | done |
| 2 | States | done |
| 3 | Lift engine and synthetic data | not started |
| 4 | Recommend, recover, privacy | not started |
| 5 | Baselines, evaluation, fairness | not started |
| 6 | App | not started |
| 7 | Docs | not started |
| 8 | Planner (optional) | not started |

## Gate results
- Gate 1 (variety): PASS on full data. 8 of 8 candidates have share >= 0.30. The lowest are glossary (0.432) and ouwiki (0.440). The sample scope has 6 of 8. Report: `reports/gate1_variety.md`.
- Gate 2 (synthetic truth): not run.
- Gate 3 (coverage): not run.

## Decisions and deviations
- Phase 0: The build runs on Windows 11 with Git Bash, not on Arch Linux. Make targets use single `uv run` lines, so they work in sh and in cmd.
- Phase 0: GNU make 4.4.1 comes from `winget install ezwinports.make` at user scope. The installer adds its folder to the user PATH. Shells that started before the install do not see it.
- Phase 0: uv installed CPython 3.12.13. `.python-version` pins 3.12.
- Phase 0: The build backend is uv_build. Without a backend, uv does not install the package, and `python -m liftpath.cli` fails.
- Phase 0: `config.py` rejects missing and unknown keys in config.yaml. It also rejects a scope that is not full, sample or synthetic.
- Phase 0: `check_dashes.py` also checks `.yml` files and skips `.git` and the tool cache directories.
- Phase 0: CLAUDE.md, BUILD.md and `.claude/` stay local. They are in `.git/info/exclude`.
- Phase 1: URL 1 (analyse.kmi.open.ac.uk) returned a response that is not a zip. URL 2 (UCI, 46.7 MB) worked. The script extracted the archive, nested zips included, and found the 7 CSVs.
- Phase 1: All 7 CSV headers match SPEC section 2. SPEC section 2 now marks the headers and the row count as verified.
- Phase 1: Full canonical row counts: courses 22, enrollments 32,593, items 6,364, events 10,655,280, assessments 206, submissions 173,912. Events are 0.5% above 10.6 million, inside the 5% limit.
- Phase 1: 11 Exam rows have no date. The adapter sets their due_day to the course length (SPEC section 2). No TMA or CMA row has a NULL date.
- Phase 1: Events keep the raw rows. The adapter does not merge repeated (student, item, day) rows. Phase 2 aggregates by week.
- Phase 1: All integer columns are BIGINT. The synthetic adapter in Phase 3 must use `liftpath.schema.CANONICAL` too.
- Phase 1: The adapter fails if a join changes a row count, if a student key repeats, or if final_result or assessment_type has a value that SPEC section 2 does not list. Casts use CAST, not TRY_CAST.
- Phase 1: Sample modules are AAA (748 enrollments, 2 presentations) and GGG (2,534 enrollments, 3 presentations). The sample also requires 2 or more presentations per module, so that a test split exists. This rule did not change the result.
- Phase 1: 45 enrollments have no reg_day. Every event row matches an item.
- Phase 2: Effort percentile ties use the average rank (`rank(method="average", pct=True)`). SPEC section 7 does not define ties. With the min or max rank, small click counts would move between the low and mid bands.
- Phase 2: The effort rank population is all students with clicks > 0 in that (course_id, week), before the registration filter.
- Phase 2: score_band counts banked submissions. known_day uses due_day if submit_day is NULL, and submit_day if due_day is NULL. A score known before day 0 counts from week 0.
- Phase 2: Cumulative scores and click shares use all weeks before the registration filter. A late registrant keeps the clicks and scores from before registration.
- Phase 2: The Gate 1 share uses all train points as the denominator. The numerator is the train points in level 0 cells where n_did >= min_count and n_did_not >= min_count. n_did and n_did_not use the SPEC section 10 band rules: next_effort_band "none" is excluded, and a band counts only if n1 >= 1 and n0 >= 1. `check_variety` has its own copy of these rules. The Phase 3 `estimate_lifts` must give the same counts.
- Phase 2: `reports/gate1_variety.md` is for the full scope. Other scopes write `reports/gate1_variety_<scope>.md`, so a sample run does not overwrite the gate report.
- Phase 2: No module has only one presentation. The test presentations are the seven `*_2014J` courses.
- Phase 2: Full candidates: oucontent, forumng, quiz, subpage, resource, ouwiki, url, glossary. The sample has dataplus in place of ouwiki.
- Phase 2: Full decision points: 898,212 (587,671 train, 310,541 test). `make states` takes 9 s on full data.
- Phase 2: `LEVELS` is in `lift.py` now. Phase 3 adds the estimator to the same file.

## Blocked
- None.

## Method issues
- None.
