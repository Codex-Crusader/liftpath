# LiftPath method

This document explains how LiftPath computes a recommendation, a route, a rescue card, a rescue map and the simulator results. `SPEC.md` holds the exact rules. All thresholds come from `config.yaml`. The values below are the shipped values.

## 1. Data and split

LiftPath uses OULAD: 7 modules, 22 presentations (course runs) and 32,593 enrollments. For each module, the latest presentation (2014J) is the test set. All earlier presentations are the training set. No outcome of a test student enters a recommendation, a route, an item ranking or a graph.

## 2. Decision points and state

A decision point is one student in one week w of one presentation. The student must be registered at the end of the week, day 7w + 6. A state at week w uses only data up to that day.

The state has four parts:

- Module (for example AAA).
- Week block: early, mid or late, by the third of the course that holds week w.
- Score band: the mean of the assessment scores known by the end of week w. A score is known on the later of the submit day and the due day. Bands: none (no score yet), low (below 40), mid (below 70) and high.
- Effort band: the clicks in week w. Zero clicks gives none. Other students are ranked within the same presentation and week: the lowest third is low, the middle third is mid, the top third is high.

The actions are the 8 activity types with the most training clicks: course pages, discussion forum, quizzes, section pages, files, wiki, external links and glossary. A student "did" an action if the student clicked that type in week w + 1.

Goals: pass (final result Pass or Distinction) and distinction. A withdrawn student reaches neither goal.

## 3. Lift estimator

Engaged students do more of everything, and they pass more. So a plain "students who did X passed more" result rewards effort, not the activity. LiftPath compares students who studied about as much in the week of the advice.

For a cell c (a group of states) and an action a, take each next-week effort band e except none:

- n1, k1: points that did a, and how many reached the goal.
- n0, k0: points that did not do a, and how many reached the goal.
- u1, u0: the number of distinct students in each group.

A band counts only if n1 >= 1 and n0 >= 1. With p_c the goal rate of the cell and m = 10 (the prior strength):

```
p1  = (k1 + m * p_c) / (n1 + m)
p0  = (k0 + m * p_c) / (n0 + m)
w   = n1 * n0 / (n1 + n0)
var = p1 (1 - p1) / (u1 + m) + p0 (1 - p0) / (u0 + m)

lift = sum(w * (p1 - p0)) / sum(w)
se   = sqrt(sum(w^2 * var)) / sum(w)
95% range = lift +/- 1.96 * se
```

The smoothing pulls a small group toward the cell rate. The weight w gives more weight to bands where both groups are large.

## 4. Recommendation rule

Cells back off from specific to wide:

- Level 0: module, week block, score band, effort band.
- Level 1: module, score band, effort band.
- Level 2: score band, effort band.

An action is supported if both n_did and n_did_not are 30 or more. At the first level with a supported action, LiftPath picks the supported action with the highest lift whose range is above zero (status recommend). If no supported action has a range above zero, the status is "no clear winner", and LiftPath does not back off. If no level has a supported action, the status is abstain.

The card text gives both goal rates, the lift, the range and the two counts. A count below 5 shows as "fewer than 5".

## 5. Route

A route plans up to 4 weeks from the student's week w0, for one goal and one planned effort band e (the current band by default; none becomes low).

1. At each week, LiftPath runs the recommendation rule on the projected state. Recommend gives a step with that activity. No clear winner gives the step "Keep your current plan". Abstain stops the route.
2. The next score band comes from training students in the same module, week, score band and planned effort who did the step activity: LiftPath takes their score band one week later. If this group has fewer than 30 points, LiftPath uses all students of the same cell (the "keep" rows), then weeks w - 1 to w + 1, then all modules. If no level has support, the route stops.
3. The route carries the share of every score band, not only the most likely band. Each step recommends for the most likely band.
4. The projected goal rate of a state is the smoothed goal rate of training students who were in that state. The route value is the share-weighted rate at the final week. The typical path uses the same steps with "keep" rows only. The app shows both, with the label "Projection from past students, not a guarantee."

Each step lists up to 3 items of the step type from the student's own course, active in the step week, ranked by total clicks. The schedule is rebuilt from course activity. A real learning management system has the exact calendar.

The app does not get the raw transition counts. `make plan` turns them into lookup tables of rates (next-band shares and goal rates). Routes from the tables match routes from the raw counts in 200 of 200 tests.

## 6. Rescue card and rescue map

A low score is a score below 40 on assessment k when assessment k + 1 exists. The recovery window is the days after the due day of k up to the due day of k + 1. Old material is the items that were active before the due day of k. The treatment "went back to type a" means the student clicked old material of type a in the window. The goal is a score of 40 or more on assessment k + 1. Effort is the total clicks in the window, banded within the presentation and assessment. The same lift estimator and rule give the rescue card.

The rescue map uses the same data per assessment. An edge from an activity type to an assessment needs 20 or more students in both groups and a positive lift. The edge is solid if the range is above zero, else dashed. The keystone of a module is the type with the highest summed lift over solid edges.

A shuffle test moves the goal values at random within each assessment and effort band, 100 times. 19% of these runs give 2 or more solid edges, as many as the real data. So the 2 solid edges can be chance.

## 7. Evaluation

Each recommender gives one action (or none) per test point. A follower is a test student who did the recommended action next week. Follower lift compares followers with non-followers in the same level 0 cell and next-week effort band, with the same weights as above. A bootstrap that resamples test students (200 runs) gives the 95% range.

Random advice also shows a positive follower lift, because engaged students do more of everything. Net lift is the follower lift minus the follower lift of random advice, with a paired bootstrap range. The common subset is the test points where every recommender gives an action.

Baselines: random, popular (most used in the same cell), course_order (most used in the same module and week), raw_success (highest success rate among users, no effort control and no comparison group) and user_cf (most used among the 50 nearest training students by activity mix, the "similar students" advice).

## 8. Simulator

The simulator makes synthetic students with a known truth, week by week. Each student has a hidden ability u. Weekly clicks and activity use depend on u. Only quizzes change the outcome: each quiz week adds 0.35 to the log-odds of a pass. Forum use rises with effort but has no effect.

- Standard world: the rules above.
- Hidden confounder world: files ("resource") are used more by students with high u, with no link to effort. Files have no effect, so effort control cannot remove this bias.

Cohort 0 gets no advice and is the shared history. Each policy has its own track: for cohort k, it learns from cohort 0 and its own cohorts 1 to k - 1, then advises cohort k. 60% of students follow the advice. All policies use the same random numbers per world and cohort, so a difference comes only from the policy. There are 6 cohorts of 1,000 students per world.

## 9. Learning loop and Wald estimate

LiftPath + explore picks a random activity for 20% of decisions and remembers that the advice was random. Random advice is an experiment: students who got advice a and students who did not differ only by chance. The Wald estimate turns this into an effect of the activity:

```
ITT_a    = mean goal (advice = a) - mean goal (advice != a)
FS_a     = mean did a (advice = a) - mean did a (advice != a)
effect_a = ITT_a / FS_a
```

ITT is the effect of the advice. FS (the first stage) is how much the advice changes use. The estimate is used only if FS_a is 0.1 or more and both arms have 30 or more decisions. A bootstrap by student (100 runs) gives the range. For the other 80% of decisions, LiftPath + explore recommends the action with the highest score whose range is above zero. The score is the experimental effect if one exists, else the observational lift.

The true effect line in the app is the cohort mean of sigmoid(logit + 0.35) - sigmoid(logit). Under fully random advice, the Wald range holds the true effect in 9 of 10 seeds. In the explore track, the experimental estimate sits above the true effect in all 8 cohort estimates. The hidden-world win of LiftPath + explore depends on this upward bias. With an explore share of 0.4, the estimates are near the truth, and the loop does not move to quizzes.

## 10. Live mode

Demo mode keeps students, activity, scores, advice and outcomes in a SQLite file. A student's state uses the same rules. Effort bands use fixed cutoffs per module and week from the training data. These cutoffs give the stored band for 94.2% of training points. A refresh adds live students with a final result to the training points and rebuilds the lift tables. The refresh rejects test points.
