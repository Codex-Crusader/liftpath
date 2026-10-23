# LiftPath model card

## Summary

LiftPath recommends the next study activity type for a student, for the goal pass or distinction. It is a set of counting rules, not a trained neural model. For each state, it compares past students who did an activity next week with past students who did not, inside the same next-week effort band. It recommends an activity only when the lift has a 95% range above zero and both groups have 30 or more student-weeks. The method is in `docs/method.md`.

Developer: Bhargavaram Krishnapur, PulseEngine. Version: 0.1.0 (DataNova 2026 data-thon). License: MIT.

## Intended use

- Decision support for students, tutors and course teams: a suggested next activity, a 4-week route and a "go back" card after a low score, each with its evidence.
- A teacher can open the "Why?" table and audit each number by hand.
- The teacher view sorts a class by facts from the course log only: a low mark on the last assessment, then weeks without clicks. It does not use a prediction of the final result.
- LiftPath supports decisions. It does not make them. It does not predict, grade or score students.

Uses that are out of scope:

- Automatic decisions about a student (admission, progression, funding, support eligibility).
- A claim that an activity causes success. Lift is evidence, not proof of cause.
- Courses or institutions unlike the training data, without a new evaluation on their own data.

## Inputs and outputs

Input: module, week, score band so far, effort band this week, and the goal. Live mode builds these from logged clicks and scores.

Output: a status (recommend, no clear winner, abstain), the activity, the lift, the 95% range, the two goal rates and the two counts. A route adds up to 4 steps and a projected goal rate, labeled "Projection from past students, not a guarantee."

## Data

Open University Learning Analytics Dataset (OULAD), 7 modules, 2013 and 2014. Training: 587,671 decision points from the earlier presentations. Test: 310,541 decision points from the seven 2014J presentations (10,203 students). Details: `docs/datasheet.md`.

## Metrics

- Follower lift: goal rate of test students who did the advised activity next week minus the rate of those who did not, in the same cell and next-week effort band.
- Net lift: follower lift minus the follower lift of random advice. Random advice has a positive follower lift (+0.3 pp for pass), because engaged students do more of everything.
- Coverage: the share of test student-weeks that get an activity.
- Ranges: 95% bootstrap over test students (200 runs).

## Results (test students)

| goal | LiftPath net lift | 95% range | LiftPath coverage | user_cf net lift | raw_success net lift |
|---|---|---|---|---|---|
| pass | +2.9 pp | +2.2 to +3.6 pp | 61.8% | +0.2 pp | +1.9 pp |
| distinction | +5.9 pp | +4.6 to +7.0 pp | 54.3% | +1.0 pp | +3.0 pp |

- LiftPath and user_cf ("similar students" advice) give different activities for 76.2% of common test student-weeks (pass) and 78.7% (distinction).
- For the pass goal, on the common subset, LiftPath minus raw_success is +0.3 pp (95% range -0.5 to +1.2 pp). LiftPath does not beat raw_success there. For distinction, the difference is +1.9 pp (+0.9 to +2.6 pp).
- On synthetic data with a known answer, LiftPath sends 0% of its recommendations to the forum (no true effect). raw_success sends 43.5% there.

## Subgroup results (goal: pass)

The follower lift is positive for every group with 200 or more students, except students with an unknown deprivation band (imd_band "unknown", 374 students): -0.9 pp, 95% range -3.2 to +1.7 pp. The ranges for imd_band 30-40% and 90-100% include zero. Age band 55 and over has 91 students (small sample). The recommend share is 59.5% to 63.8% in all groups of 200 or more students, and 49.1% for age 55 and over. Full table: `reports/fairness.md`.

## Limitations

- The data is observational. Lift is evidence, not proof of cause.
- Effort control removes "how much" bias, not all bias. On synthetic data, the pooled forum lift (+6.3 pp) is above the quiz lift (+3.9 pp), although only quizzes help. The level 0 tables that the app uses rank quizzes higher (+4.2 pp against +3.3 pp), but this is a diagnostic, not a test result.
- Scores count from the later of the submit day and the due day. Real marking takes longer.
- Activity types are coarse. Some activities are not open every week.
- One university, 2013 and 2014 data.
- LiftPath compares several activities per state. Some winners can be chance results.
- Routes use score transitions of past students. A route projection is not a forecast for one student.
- The rescue map has 2 solid edges, and a shuffle test gives 2 or more in 19% of runs. The edges can be chance.
- The simulator win of the explore loop in the hidden confounder world depends on an upward bias of its experimental estimate.

## Ethics and privacy

- The committed app data holds no count below 5 and no student outcome. OULAD student ids are pseudonymous. LiftPath adds no other identifier.
- No outcome of a test student enters a recommendation, a route, an item ranking or a graph.
- A recommendation names an activity type, never a person. LiftPath does not predict a student's result.
