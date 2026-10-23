# LiftPath progress

## Status
| Phase | Name | Status |
|---|---|---|
| 0 | Setup | done |
| 1 | Data | done |
| 2 | States | done |
| 3 | Lift engine and synthetic data | done (Gate 2 test 2 fails) |
| 4 | Recommend, recover, privacy | done |
| 5 | Baselines, evaluation, fairness | done |
| 6 | App | done |
| 7 | Docs | replaced by BUILD2 |
| 8 | Planner (optional) | replaced by BUILD2 |
| A | Route | done |
| B | Simulator and learning loop | not started |
| C | Trap comparison | not started |
| D | Live mode and engine CLI | not started |
| E | Rescue map | not started |
| F | App restructure | not started |
| G | Presentation package and docs | not started |

## Gate results
- Gate 1 (variety): PASS on full data. 8 of 8 candidates have share >= 0.30. The lowest are glossary (0.432) and ouwiki (0.440). The sample scope has 6 of 8. Report: `reports/gate1_variety.md`.
- Gate 2 (synthetic truth): FAIL on test 2. The user chose to keep SPEC and continue.
  - Test 1 PASS: raw P(pass | act_forumng) = 0.633 > P(pass | act_quiz) = 0.526 (train points).
  - Test 2, ci_low(quiz) > 0: PASS. Pooled quiz lift 0.039 (95% range 0.015 to 0.063).
  - Test 2, lift(quiz) > lift(forumng): FAIL. Pooled forumng lift 0.063 (95% range 0.036 to 0.089). `tests/test_synthetic.py` marks it as a strict xfail.
  - The leakage test passes.
- Gate 3 (coverage): PASS on full data. LiftPath status is not abstain for 100.0% of test points (pass goal). The gate needs 50%. The recommend share (the share that gets an action) is 61.8%.

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
- Phase 3: The estimator output also has an `se` column. The hand example test checks it.
- Phase 3: `estimate_lifts` counts unique students as unique (course_id, student_id) pairs (SPEC section 2 key).
- Phase 3: A cell where no effort band has n1 >= 1 and n0 >= 1 gets no row in the lift table.
- Phase 3: `best_actions` returns, per level, only the cells with a supported candidate. `resolve_points` does the back-off from level 0 to level 2. no_clear_winner stops the back-off. Ties on lift go to the first action name.
- Phase 3: Synthetic generator choices that SPEC section 16 does not fix:
  - q counts quiz weeks that end before the due day (7w + 6 < due_day).
  - The submit day is the due day.
  - A student who withdraws in week W keeps events up to week W. unreg_day = 7W + 6, and no submission is due after it.
  - Student ids are 1 to 1500 in 2013J and 1501 to 3000 in 2014J.
- Phase 3: The quiz effect stays at 0.35. The allowed change to 0.5 did not pass the gate (quiz 0.057, forumng 0.067), so I did not keep it.
- Phase 3: `make lifts` writes `lifts/<goal>_level<L>.parquet` and `lifts/best_<goal>_level<L>.parquet` to the scope directory. It uses train points only. Full data: 1,849, 736 and 128 lift rows at levels 0, 1 and 2. Test status shares for goal_pass: recommend 0.618, no_clear_winner 0.382, abstain 0.
- Phase 4: Rationale text follows the SPEC section 12 template. Two wording choices: score_band "none" shows as "no scores yet", and effort_band "none" shows as "no activity this week". The template text "none scores" and "none effort" is not readable.
- Phase 4: Goal words in the text: goal_pass is "a pass", goal_distinction is "a distinction", goal_recover is "a pass mark on the next assessment".
- Phase 4: `best_actions` and `resolve_points` take an optional `levels` argument. Recovery uses `RECOVERY_LEVELS` = {0: (module, low_band), 1: (low_band)}.
- Phase 4: `states.effort_bands` takes the group columns as an argument. Recovery effort bands use (course_id, assessment_id).
- Phase 4: `recover.VERY_LOW_MAX = 20` comes from SPEC section 13. config.yaml has no key for it, and BUILD.md fixes the config content.
- Phase 4: Recovery ordering uses non-Exam assessments with a due_day, ordered by due_day and then assessment_id. The window starts at due_day k, also when the student submitted k late. An item with no week_from and no clicks has no active day, so it is never old material.
- Phase 4: SPEC section 13 has no rationale template for recovery. `explain_recovery` uses the section 12 style: "those who went back to earlier <label>". Level 1 adds "(compared across all courses)".
- Phase 4: `suppress_counts` also hides a count of 0, because 0 is below display_min_count. It keeps an earlier `suppressed` flag when you call it again.
- Phase 4: Full recovery points: 6,159 (3,892 train, 2,267 test), no repeated keys. Recovery rate (goal_recover): 0.497. Test status shares: recommend 0.862, no_clear_winner 0.138.
- Phase 4: The recovery effort rank population is the triggered points (score below low_score, a next assessment exists) with window clicks > 0, within (course_id, assessment_id). SPEC section 13 does not say whose clicks form the ranking.
- Phase 4: Two of the three demo cards recommend the discussion forum. This agrees with the Phase 3 method issue: tertile effort control can rate effort-driven actions too high.
- Phase 5: popular backs off to the next level when a cell has fewer than min_count train points. course_order gives None for a (module, week) with no train points. SPEC section 14 does not say either.
- Phase 5: raw_success scores a candidate only if n1 >= min_count. If only one candidate qualifies in a cell, it wins, also with a low success rate.
- Phase 5: user_cf: a cum_share vector of zeros has cosine similarity 0 with every train point. Ties among neighbors follow numpy argpartition order. Test rows go in chunks of 2,000.
- Phase 5: Every recommender uses the same bootstrap draws (students drawn with replacement over all test students, n_boot runs, seed from config). Net lift gets a paired percentile range from the per-run differences (R minus random). The range uses the coverage that z gives (z = 1.96 gives 95%).
- Phase 5: `make eval` builds the LiftPath tables from train points. It does not read the tables on disk.
- Phase 5: Fairness joins demographics from enrollments. A NULL imd_band is the group "unknown". The small-sample flag counts unique students (n < 200). `fairness.SMALL_SAMPLE_STUDENTS = 200` comes from SPEC section 17.
- Phase 5: Report names: the full scope writes `reports/eval.md`, `eval_results.json`, `fairness.md` and `figures/eval_lift.png`, `figures/fairness.png`. Other scopes add `_<scope>`. The synthetic run also writes `figures/synthetic_truth.png` and a ground truth table.
- Phase 5: Figure colors: LiftPath is blue (#2a78d6) and raw_success is orange (#eb6834) in every figure. The pair passed the dataviz palette validator (light mode).
- Phase 5: `evaluate_all` takes an optional `reference`. The reports add a "LiftPath minus each recommender" table with paired ranges.
- Phase 5: A rerun of `make eval` gives the same reports and figures. The bootstrap is deterministic under the config seed.
- Phase 5: `make all` does not build the synthetic scope. Phase 6 must use the committed `reports/figures/synthetic_truth.png`, or `make all` must add the synthetic steps.
- Phase 5: `make eval` takes 38 s on full data and 10 s on synthetic data.
- Phase 5 results, full data, net lift (minus random) with 95% range:
  - Pass: LiftPath +2.9 pp (+2.2 to +3.6). raw_success +1.9 pp (+1.3 to +2.6). course_order +1.8 pp (+1.1 to +2.6). On the common subset: LiftPath +3.0 pp (+2.3 to +3.7), raw_success +2.7 pp (+1.7 to +3.6). The ranges overlap.
  - Distinction: LiftPath +5.9 pp (+4.6 to +7.0). raw_success +3.0 pp (+2.1 to +4.3). On the common subset: LiftPath +5.9 pp (+4.6 to +7.1), raw_success +4.0 pp (+2.7 to +5.7).
  - LiftPath minus raw_success, paired bootstrap: pass +1.0 pp (+0.5 to +1.7) on all test points, +0.3 pp (-0.5 to +1.2) on the common subset. Distinction +2.8 pp (+1.9 to +3.7), and +1.9 pp (+0.9 to +2.6) on the common subset. For the pass goal, LiftPath does not beat raw_success on the common subset.
  - LiftPath status shares (pass): recommend 61.8%, no_clear_winner 38.2%, abstain 0.0%.
- Phase 5 results, synthetic data:
  - Ground truth (pass goal, test points): quiz share of recommendations: LiftPath 63.0%, raw_success 21.1%, random 12.2%, popular 60.8%, course_order 82.2%, user_cf 19.9%. forumng share: LiftPath 0.0%, raw_success 43.5%.
  - course_order and popular pick quiz often because quiz is a common activity in the generator, not because they measure its effect.
  - Net lift (pass): LiftPath +2.0 pp (-0.2 to +4.3), raw_success +2.3 pp, course_order +2.7 pp. Follower lift ranks raw_success above LiftPath here, although raw_success sends 43.5% of its picks to forumng, which has no effect. Follower lift uses the same effort bands as LiftPath and can reward effort-driven picks. Present the ground truth table next to follower lift.
- Phase 5 fairness (full, pass): follower lift is positive in every group with 200 or more students except imd_band "unknown" (-0.9 pp, range -3.2 to +1.7). age_band 55<= has 91 students (small sample).
- Phase 6: `lift.band_table` now holds the per band counts and rates. `estimate_lifts` uses it. On full data the level 0, 1 and 2 tables are the same as before (1,849, 736 and 128 rows).
- Phase 6: `make eval` also writes `reports/fairness_results{suffix}.json`, so app-data can read the fairness table.
- Phase 6: `make app-data` writes to `data/app/` for the full scope only. Other scopes write to `data/tmp/app_<scope>/`, so they never replace the committed app data. Full app data: 24 files, 0.98 MB.
- Phase 6: App data contents: lift and best-action tables per goal and level, the level 0 audit bands, sampled test students (state columns and recommendations only, no outcomes and no activity flags), recovery test points with their recommendation, recovery tables, eval results, the fairness table, figures and `meta.json`. Counts below display_min_count are NULL. In the audit table, p1 and p0 are NULL in a suppressed row.
- Phase 6: The app sorts students by their number of level 0 recommendations, then by all recommendations. It opens on the first level 0 recommended week, so the first card uses the most specific evidence.
- Phase 6: SPEC section 19 allows the OULAD student ids in `data/app/`, because they are already pseudonymous. The app data adds no other identifiers.
- Phase 6: The app shows lifts in percentage points (pp). The card text from `recommend.explain` keeps whole percent, as in SPEC section 12.
- Phase 6: The app uses the committed `reports/figures/synthetic_truth.png`. `make all` still does not build the synthetic scope.
- Phase 6: The Teacher audit tab also shows the cell lift from the level 0 table. A hand check on one cell (AAA, early, high, high, forum) gives the same value (-2.0 pp).
- Phase 6: `tests/test_app.py` builds synthetic app data in a temp folder from the generator and the committed synthetic eval reports, runs the app with AppTest, and also runs it with the distinction goal.
- BUILD2: The user gave BUILD2 (phases A to G). It replaces BUILD.md Phase 7 and 8. BUILD2.md stays local like BUILD.md (`.git/info/exclude`). The BUILD2 config keys are in config.yaml and in `Config`. `sim_worlds` loads as a tuple.
- Phase A: `route.score_transitions` links each train point to the same student at week + 1. It counts (module, week, score_band, next_effort_band, action) to (next_week_block, next_score_band), with n and goal counts k_goal_pass and k_goal_distinction. The action `_keep` holds all points. Rows with next_effort_band "none" are left out, because a plan effort is never "none".
- Phase A: Projection back-off: level 0 is (module, week). Level 1 is (module, weeks w-1 to w+1). Level 2 is all modules, weeks w-1 to w+1. A level needs n >= min_count. The next score band is the mode. Ties go to the lower band. The next week block is the mode of the module's own KEEP rows at week w.
- Phase A: Each step projects one week forward, also the last step. So the final projected state is at week w0 + plan_horizon_weeks.
- Phase A: The projected goal rate of a state (module, week, score, effort) uses the targets of KEEP transitions from week - 1 (effort_band at week w equals next_effort_band at w - 1). Smoothing: (k + m * prior) / (n + m), where the prior is the goal rate of all targets in the same scope. The scope backs off like a projection. The typical rate projects score bands with KEEP from the same start to the same final week.
- Phase A: A route stops when recommend() abstains, when a projection has no support, or when the week is past the last transition week of the module ("The course ends at week N").
- Phase A: `item_schedule` returns course_id, item_id, item_type, action, active_day, active_week and clicks, ordered by (course_id, item_id). action and active_day are extra columns: action maps item types (fallback groups), and active_day is needed for rescue items. Items with no active day (no week_from and no clicks) are left out: full data has 6,268 of 6,364 items.
- Phase A: Step items: items of the step type in the student's course at the step week. If there are none, the items at distance 1 week. Top 3 by total clicks. KEEP steps have no items.
- Phase A: `rescue_card` uses the recovery point whose window holds the end of the student's week (due_day <= week_end < next_due_day), with score < low_score and status recommend. Items: old items of that type (active_day < due_day), top 3 by clicks. The app copy of recovery points has no due_day and next_due_day. Phase F must add them to `app_data.RECOVERY_COLS`.
- Phase A: `make plan` writes `plan/transitions.parquet` and `plan/schedule.parquet` in the scope folder. Full data: 21,403 transition rows and 6,268 items. `make all` now runs `plan` before `app-data`.
- Phase A: One route takes 0.125 s on full data. On 300 seeded full test points (pass goal), 261 routes have 4 steps, 72% have a recommend step, and 45% show items. Stop reasons: horizon 253, course end 31, no projection 16.
- Phase A: `scripts/demo_cards.py` prints 2 full routes (they reach the horizon and have a recommend step with items). The pool puts test points inside the window of a rescue recommendation first (due_day <= week_end < next_due_day). Both printed routes (BBB_2014J week 18, FFF_2014J week 17) show a rescue card with items. An earlier pool printed the GGG route in Method issues.

## Blocked
- None.

## Method issues
- Phase A: Route and typical projections are equal for 98.3% of routes (pass) and 98.0% (distinction), on 300 seeded full test points. The mean gap (route minus typical) is +0.59 pp (pass) and +0.16 pp (distinction). Reason: a route changes the projection only through the next score band, and the band seldom changes in one week. A Phase F "route vs typical" chart will mostly show two equal values. Ask the user.
- Phase A: The week-window back-off can mix weeks before and after an assessment due date. Example: an earlier demo route (GGG_2014J, student 573320, week 5, forum). Forum users have too few rows at level 0, so the projection uses weeks w-1 to w+1. At week 7 this mixes week 6 (no scores yet, 9 rows) with weeks 7 and 8 (scores, 10 rows), and the mode says "none". The route then projects a pass rate of 50.9% against 78.3% for the typical path. The method is unchanged. Ask the user.
- Phase 3: Next-week effort control in tertiles leaves confounding for an action that rises with effort. On synthetic data, forumng has no true effect, but its pooled lift (0.063) is above the quiz lift (0.039). Inside a tertile, forum use still rises with clicks, and clicks rise with ability. Diagnostics with a ceil(pct * bins) rule show finer bins reduce the forumng lift but do not remove it: 5 bins give quiz 0.030 and forumng 0.040, and 10 bins give quiz 0.031 and forumng 0.034. A probe on level 0 cells (current effort and score band in the cell) gave quiz 0.041 and forumng 0.032, but it has no interval and is not a gate result. The user chose to keep SPEC sections 7 and 10. Phase 5 net lift and the synthetic truth figure must show this result.
- Phase 5 (check before the phase): The shipped method uses level 0 cells, and it finds the true effect on synthetic data. This is a diagnostic, not a gate result. The level 0 lift tables (train points, cells with min(n_did, n_did_not) >= min_count) give a w-weighted mean lift of 0.042 for quiz (ci_low 0.026) and 0.033 for forumng. The combined se assumes independent cells, but the cells share students. On synthetic test points, LiftPath recommends quiz in 63% of its recommendations, url in 29%, glossary in 8% and forumng in 0%. The url and glossary picks are the SPEC section 20 limitation "Some winners can be chance results". The method stays as SPEC defines it.
- Phase 4: The SPEC section 12 template says "Based on {n_did} and {n_did_not} students", but n_did and n_did_not count decision points (student-weeks). At level 1 and 2 they also add up across weeks. The text keeps the SPEC wording for now. Phase 6 and 7 must fix the wording or show unique students (u1 and u0, which the estimator already computes), with the user's agreement. Phase 6: the app tables and the audit caption say "student-weeks". The card text still says "students" (SPEC wording).
