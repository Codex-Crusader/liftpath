# LiftPath progress

## Status
| Phase | Name | Status |
|---|---|---|
| 0 | Setup | done |
| 1 | Data | done |
| 2 | States | not started |
| 3 | Lift engine and synthetic data | not started |
| 4 | Recommend, recover, privacy | not started |
| 5 | Baselines, evaluation, fairness | not started |
| 6 | App | not started |
| 7 | Docs | not started |
| 8 | Planner (optional) | not started |

## Gate results
- Gate 1 (variety): not run.
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
- Phase 1: URL 1 (analyse.kmi.open.ac.uk) returned a response that is not a zip. URL 2 (UCI, 46.7 MB) worked. The 7 CSVs were in a nested zip.
- Phase 1: All 7 CSV headers match SPEC section 2. SPEC section 2 now marks the headers and the row count as verified.
- Phase 1: Full canonical row counts: courses 22, enrollments 32,593, items 6,364, events 10,655,280, assessments 206, submissions 173,912. Events are 0.5% above 10.6 million, inside the 5% limit.
- Phase 1: 11 Exam rows have no date. The adapter sets their due_day to the course length (SPEC section 2). No TMA or CMA row has a NULL date.
- Phase 1: Events keep the raw rows. The adapter does not merge repeated (student, item, day) rows. Phase 2 aggregates by week.
- Phase 1: All integer columns are BIGINT. The synthetic adapter in Phase 3 must use `liftpath.schema.CANONICAL` too.
- Phase 1: The adapter fails if a join changes a row count, if a student key repeats, or if final_result or assessment_type has a value that SPEC section 2 does not list. Casts use CAST, not TRY_CAST.
- Phase 1: Sample modules are AAA (748 enrollments, 2 presentations) and GGG (2,534 enrollments, 3 presentations). The sample also requires 2 or more presentations per module, so that a test split exists. This rule did not change the result.
- Phase 1: 45 enrollments have no reg_day. Every event row matches an item.

## Blocked
- None.

## Method issues
- None.
