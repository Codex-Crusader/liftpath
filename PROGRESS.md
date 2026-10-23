# LiftPath progress

## Status
| Phase | Name | Status |
|---|---|---|
| 0 | Setup | done |
| 1 | Data | not started |
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

## Blocked
- None.

## Method issues
- None.
