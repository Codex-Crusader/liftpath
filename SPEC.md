# LiftPath specification

## 1. Purpose
LiftPath recommends the next study activity for a student. It ranks activities by measured lift toward the student's goal. Lift compares matched students: same situation, same study effort next week, different activity choice. Each recommendation shows its counts. When data is too thin, LiftPath abstains.

Pitch: "Not what students like you did. What helped students like you."

## 2. Source data: OULAD
- Name: Open University Learning Analytics Dataset.
- License: CC BY 4.0. Cite: Kuzilek J., Hlosta M., Zdrahal Z. "Open University Learning Analytics dataset." Scientific Data 4, 2017. (Verify the citation details in Phase 7.)
- Files and headers (verified in Phase 1 against the UCI download):

| File | Columns |
|---|---|
| courses.csv | code_module, code_presentation, module_presentation_length |
| assessments.csv | code_module, code_presentation, id_assessment, assessment_type, date, weight |
| vle.csv | id_site, code_module, code_presentation, activity_type, week_from, week_to |
| studentInfo.csv | code_module, code_presentation, id_student, gender, region, highest_education, imd_band, age_band, num_of_prev_attempts, studied_credits, disability, final_result |
| studentRegistration.csv | code_module, code_presentation, id_student, date_registration, date_unregistration |
| studentAssessment.csv | id_assessment, id_student, date_submitted, is_banked, score |
| studentVle.csv | code_module, code_presentation, id_student, id_site, date, sum_click |

- Known quirks:
  - "?" means missing. Treat "?" and empty as NULL.
  - Days are relative to the presentation start. They can be negative.
  - Exam rows in assessments.csv can have no date. Use the course length.
  - Most week_from and week_to values are missing.
  - is_banked = 1 means the score came from an earlier attempt.
  - One student can be in several presentations. The key is (course_id, student_id).
  - final_result values: Pass, Distinction, Fail, Withdrawn.
  - assessment_type values: TMA, CMA, Exam.
- studentVle row count: 10,655,280 (verified in Phase 1).

## 3. Canonical schema
Parquet files in `data/processed/<scope>/canonical/`. Every adapter (OULAD, synthetic, future organizer data) must produce exactly these tables.

`course_id = code_module + "_" + code_presentation`

| Table | Columns (type) |
|---|---|
| courses | course_id (str), module (str), presentation (str), length_days (int) |
| enrollments | course_id, module, presentation, student_id (int), reg_day (int, null), unreg_day (int, null), final_result (str), gender, age_band, imd_band, disability, region, highest_education (str, null) |
| items | course_id, item_id (int), item_type (str), week_from (int, null), week_to (int, null) |
| events | course_id, student_id, item_id, day (int), clicks (int) |
| assessments | course_id, assessment_id (int), kind (str), due_day (int, null), weight (float) |
| submissions | course_id, student_id, assessment_id, submit_day (int, null), score (float, null), banked (bool) |

Demographic columns are used only by the fairness report. They are never part of a state.

## 4. Data scopes
- `full`: all OULAD data.
- `sample`: the two modules with the fewest enrolled students, all their presentations.
- `synthetic`: data from the synthetic generator (section 16).

## 5. Train and test split
For each module: the latest presentation (string sort of `presentation`) is test. All earlier presentations are train. A module with one presentation goes to train only. Log it.

## 6. Decision points
- `n_weeks = ceil(length_days / 7)`. `week(day) = floor(day / 7)`. `week_end(w) = 7*w + 6`.
- Decision weeks: w = 0 to n_weeks - 2.
- Keep (course_id, student_id, w) only if the student is registered at week_end(w): reg_day is NULL or reg_day <= week_end(w), and unreg_day is NULL or unreg_day > week_end(w).
- Clicks before day 0 count only toward cumulative shares.

Columns of `decision_points.parquet`:
course_id, module, presentation, split, student_id, week, week_block, score_band, effort_band, next_effort_band, clicks_week, clicks_next, cum_share_<a> (one per candidate), act_<a> (one per candidate), goal_pass, goal_distinction.

## 7. State
- `week_block`: early if w < n_weeks/3, mid if w < 2*n_weeks/3, else late.
- `score_band`: take non-Exam submissions with a score where `known_day = max(submit_day, due_day) <= week_end(w)`. If due_day is NULL, use submit_day. Compute the mean score. Bands: none (no scores), low (< 40), mid (< 70), high (>= 70).
- `effort_band`: clicks in week w. 0 gives "none". Otherwise rank among students with clicks > 0 in the same (course_id, week). Percentile <= 1/3 gives low, <= 2/3 gives mid, else high.
- `next_effort_band`: the same rule applied to clicks in week w+1, in (course_id, w+1).

Back-off levels (cells use `module`, not `course_id`, so train and test share cells):
- Level 0: module, week_block, score_band, effort_band
- Level 1: module, score_band, effort_band
- Level 2: score_band, effort_band
- No level has enough data: abstain.

## 8. Actions
- Candidates: the top `n_candidates` item types by total train clicks, excluding `exclude_types`.
- `act_<a>` is true if the student has clicks > 0 on type a in week w+1.
- `cum_share_<a>`: the student's share of clicks on type a over all days <= week_end(w).
- If `use_fallback_groups` is true, map item types to the groups in section 18 first.

## 9. Goals
- `goal_pass`: final_result in {Pass, Distinction}.
- `goal_distinction`: final_result = Distinction.
- Withdrawn counts as not reaching either goal.

## 10. Lift estimator
Generic function. Inputs: points, cell columns (can be empty), effort column, treatment columns, goal column.

For each cell c and treatment a:
- `p_c` = goal rate of all points in cell c.
- For each effort band e except "none":
  - n1, k1 = points with a = true, and how many reached the goal
  - n0, k0 = points with a = false, and how many reached the goal
  - u1, u0 = unique students in each group
  - Use band e only if n1 >= 1 and n0 >= 1.
  - `p1 = (k1 + m*p_c) / (n1 + m)`, `p0 = (k0 + m*p_c) / (n0 + m)`, with m = prior_strength
  - `w = n1*n0 / (n1 + n0)`
  - `var = p1(1-p1)/(u1 + m) + p0(1-p0)/(u0 + m)`
- `lift = sum(w*(p1-p0)) / sum(w)`
- `se = sqrt(sum(w^2 * var)) / sum(w)`
- `ci = lift +/- z*se`
- `p1_avg` and `p0_avg`: w-weighted means of p1 and p0, used in the rationale.
- `n_did = sum(n1)`, `n_did_not = sum(n0)` over the used bands.

Output columns: cell columns, action, lift, ci_low, ci_high, p1_avg, p0_avg, n_did, n_did_not, base_rate.

## 11. Recommendation rule
For a state and a goal:
1. Start at level 0. A candidate is "supported" if min(n_did, n_did_not) >= min_count.
2. If no candidate is supported, go to the next level. After level 2, return status "abstain" with the text "Not enough similar students to compare."
3. At the first level with a supported candidate, pick the supported candidate with the highest lift and ci_low > 0. Return status "recommend".
4. If no supported candidate has ci_low > 0, return status "no_clear_winner" with the text "No clear winner. Continue your current plan." Do not back off for this case.

Statuses: recommend, no_clear_winner, abstain. "Coverage" means status is not abstain.

## 12. Rationale text
Template (status recommend):
"Students in a similar situation ({module}, {week_block} weeks, {score_band} scores, {effort_band} effort) who studied about as much as you did next week: those who used {label} reached {goal} {p1_avg:.0%} of the time. Those who did not reached it {p0_avg:.0%} of the time. Lift: {lift:+.0%} (95% range {ci_low:+.0%} to {ci_high:+.0%}). Based on {n_did} and {n_did_not} students."
- Remove cell parts dropped by back-off. Add "(compared across all weeks)" at level 1 and "(compared across all courses)" at level 2.
- Show any count below display_min_count as "fewer than 5".

Labels: oucontent "course pages", resource "files", url "external links", subpage "section pages", forumng "discussion forum", quiz "quizzes", ouwiki "wiki", glossary "glossary", externalquiz "external quizzes", oucollaborate "live sessions", ouelluminate "live sessions", questionnaire "questionnaires", page "pages", dataplus "data tools", dualpane "dual-pane pages", htmlactivity "interactive pages", repeatactivity "repeat activities", sharedsubpage "shared pages", folder "folders", homepage "course homepage". Unknown type: use the raw name.

## 13. Recovery ("go back")
- Per course_id, order non-Exam assessments by due_day.
- Trigger: a student submitted assessment k with score < low_score, and assessment k+1 exists.
- Window: days in (due_day_k, due_day_k+1].
- Item active day: week_from*7 if week_from is not NULL. Else the click-weighted median click day of that item over all students in the course_id.
- Old material for k: items with active day < due_day_k.
- Treatment `rev_<a>`: the student clicked old material of type a in the window.
- Goal `goal_recover`: the student submitted k+1 with score >= low_score.
- Cells: level 0 (module, low_band), level 1 (low_band). low_band: very_low (< 20), low (20 to 39).
- Effort: total clicks in the window, banded within (course_id, assessment_id) with the section 7 rule.
- Use the same lift estimator and the same rule as section 11.

## 14. Baselines
All recommenders are vectorized: input test points, output one action per point (or None).
- random: uniform choice among candidates, seeded.
- popular: the candidate with the highest mean act in train for the same level 0 cell, with back-off.
- course_order: the candidate with the highest mean act in train for the same (module, week).
- raw_success: the candidate with the highest P(goal | cell, act = true) in train, n1 >= min_count, with back-off. No effort control and no comparison group.
- user_cf: for each test point, find the cf_neighbors nearest train points in the same (module, week) by cosine distance on cum_share_<a>. Recommend the candidate with the highest mean act among the neighbors.
- liftpath: section 11. Only status recommend gives an action.

## 15. Evaluation
Train on train points. Evaluate on test points. Primary goal: goal_pass. Secondary: goal_distinction.

For each recommender R:
- `coverage`: share of test points where R gives an action.
- `follower`: act_<R action> is true.
- Strata: (level 0 cell, next_effort_band), excluding "none".
- `follower_lift = sum(w_s * (pf_s - pn_s)) / sum(w_s)`, with `w_s = nf*nn / (nf + nn)`.
- 95% interval: cluster bootstrap that resamples students (n_boot runs, percentile method).
- `net_lift = follower_lift(R) - follower_lift(random)`.
- Also report all metrics on the common subset: test points where every recommender gives an action.
- LiftPath only: status shares (recommend, no_clear_winner, abstain).

Gate 3: LiftPath coverage (status not abstain) >= gate_coverage_min on full test data.

Note: the random recommender will show positive follower lift. Engaged students do more of everything and pass more. This is expected. Report it as the bias floor. Net lift is the honest result.

## 16. Synthetic generator
Output: the canonical tables (section 3), so the full pipeline runs on it.
- Module "SYN". Presentations "2013J" (train) and "2014J" (test), 1500 students each. length_days = 84.
- Item types: oucontent, quiz, forumng, resource, url, subpage, ouwiki, glossary, homepage. One item per type per course.
- Each student: u ~ Normal(0, 1).
- Weekly total clicks: c ~ Poisson(exp(1.8 + 0.7*u + e)), e ~ Normal(0, 0.3).
- If c > 0, engage each type with probability sigmoid(a + b*log1p(c)):
  - forumng: a = -5.0, b = 2.0 (effort-driven, no true effect)
  - quiz: a = -0.4, b = 0.0 (true effect)
  - homepage: a = 2.0, b = 0.0
  - other types: a = -1.5, b = 0.5
- Clicks for each engaged type: max(1, c // number of engaged types), on that week's days.
- Assessments: TMA due day 30, TMA due day 65 (weight 50 each), Exam due day 84 (weight 100, no submissions).
- TMA score: clip(round(55 + 15*u + 3*q + Normal(0, 10)), 0, 100), q = quiz weeks before the due day.
- Outcome: Q = total quiz weeks. logit = 0.2 + 1.5*u + 0.35*(Q - 4.8). Pass with probability sigmoid(logit). Distinction if pass and logit > 2.0.
- Withdrawals: 10% of students withdraw in a random week from 2 to 10. They get no events or submissions after that week, unreg_day set, final_result Withdrawn.
- reg_day = -10. Random demographic values.
- Seed from config.

Expected results (Gate 2 tests):
1. Pooled raw success rate: P(pass | act_forumng) > P(pass | act_quiz).
2. Pooled LiftPath lift (no cell columns, effort = next_effort_band): lift(quiz) > lift(forumng), and ci_low(quiz) > 0.

## 17. Fairness
For LiftPath on test data, by gender, age_band, imd_band and disability: coverage, recommend share, follower lift with bootstrap interval, and n. Mark groups with n < 200 as "small sample".

## 18. Fallback groups
Use these only if Gate 1 fails.
- reading: oucontent, resource, url, subpage, page, folder, dualpane, sharedsubpage, htmlactivity, dataplus
- practice: quiz, externalquiz, questionnaire, repeatactivity
- discussion: forumng, ouwiki, glossary
- live: oucollaborate, ouelluminate
- navigation: homepage (excluded)

## 19. Privacy
- Never show or store in `data/app/` a count below display_min_count. Replace it with NULL and a `suppressed` flag.
- Student ids in OULAD are already pseudonymous. Do not add other identifiers.

## 20. Limitations (use in docs)
- The data is observational. Lift is evidence, not proof of cause.
- Effort control removes "how much" bias, not all bias.
- Scores count from max(submit, due) day. Real marking takes longer.
- Activity types are coarse. Some activities are not open every week.
- One university, 2013 and 2014 data.
- Several candidates are compared per state. Some winners can be chance results.
