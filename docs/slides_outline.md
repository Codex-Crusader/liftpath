# LiftPath slides outline

Ten slides for the DataNova 2026 presentation. The figures are in `reports/slides/` (1600 x 900, from `make figures`) and `reports/figures/`. Each speaker note has 60 words or fewer. The numbers come from `reports/headline.md`, `reports/eval.md` and `PROGRESS.md`.

## Slide 1: The trap

Message: The most common advice can point to an activity that does not help.

Figure: `reports/slides/trap_example.png`

Notes: This student is in AAA, week 36. Similar students used the discussion forum. Against students with the same next-week effort, the forum lift is -5 points. Course pages give +4. On 187,992 test student-weeks, "similar students" advice and LiftPath pick different activities 76% of the time.

## Slide 2: The idea

Message: Ask what helped students like you, not what students like you did.

Figure: `reports/figures/synthetic_truth.png`

Notes: Synthetic data with a known truth: only quizzes help, and forum use follows effort. Raw success sends 43.5% of its picks to the forum. LiftPath sends none there and 63% to quizzes. The pooled middle panel still rates the forum high. Effort control in thirds removes most, not all, of the bias.

## Slide 3: Route demo

Message: A student gets a 4-week route, a "go back" card and a projected chance, each with its evidence.

Figure: `reports/slides/route_example.png`

Notes: Student 388259 in GGG scored 10 on the last assessment. First, go back to quizzes: +10 points on the next assessment. Then course pages and files, each with a range above zero. The projected pass chance is 93.5% against 91.4% for the typical path. This is a projection from past students, not a guarantee.

## Slide 4: How matched lift works

Message: LiftPath compares students only with students who studied about as much the same week.

Figure: `reports/slides/matched_lift.png`

Notes: For each next-week effort band, compare the pass rate of students who used course pages with those who did not. Small groups are pulled toward the cell rate. The lift is the weighted mean of the differences: +7.6 points, range +0.2 to +15.0. LiftPath recommends only if the range is above zero and both groups have 30 or more.

## Slide 5: Real-data evidence

Message: On 10,203 test students, LiftPath advice has the highest net lift of six methods.

Figure: `reports/slides/eval_real_data.png`

Notes: Net lift is follower lift minus the lift of random advice. For pass: LiftPath +2.9 points, raw success +1.9, similar students +0.2. For distinction: +5.9 against +3.0. LiftPath advises on 62% of student-weeks. On the common subset for pass, LiftPath and raw success are within each other's range.

## Slide 6: Simulator proof

Message: In a world with a known truth, LiftPath finds the activity that helps.

Figure: `reports/slides/sim_standard.png`

Notes: Synthetic students, 6 cohorts of 1,000. Only quizzes help. In cohort 5, LiftPath reaches 63.7% pass against 47.9% with no advice and 53.2% with similar-students advice. Over cohorts 2 to 5, popular has the best mean, because here the most used activity is also the helpful one.

## Slide 7: The learning loop

Message: A hidden trait can fool any observational method, and random exploration gives an experiment to test it.

Figure: `reports/slides/estimate_convergence.png`

Notes: In the hidden world, files have no effect, but able students use them. The observational lift for files stays at +10 to +15 points. The explore ranges for files include zero. The explore estimate for quizzes sits above the true effect, and the explore win depends on that bias. We report it, not hide it.

## Slide 8: Rescue map

Message: After a low score, going back to earlier material can help, but the evidence is thin.

Figure: `reports/slides/rescue_map.png`

Notes: In module CCC, external links before assessment 1 and section pages before assessment 3 have ranges above zero. A shuffle test gives 2 or more such edges in 23% of runs, so they can be chance. Four modules have no supported edge. The map is a question for course teams, not an answer.

## Slide 9: Fairness and limits

Message: The lift holds across groups, with one exception that we name.

Figure: `reports/slides/fairness.png`

Notes: The follower lift is positive in every group of 200 or more students, except an unknown deprivation band: -0.9 points, range -3.2 to +1.7. The data is observational, from one university in 2013 and 2014. Lift is evidence, not proof of cause. Counts below 5 never leave the build.

## Slide 10: Impact and next steps

Message: LiftPath turns the course log that every university already has into advice with its evidence attached.

Figure: `reports/slides/route_example.png`

Notes: The engine CLI gives strict JSON for a learning platform. Demo mode logs advice, so a course can run the explore loop and get an experiment. Next steps: a pilot with one course team, the real course calendar for items, and a test of the explore bias before any claim about the loop.
