# LiftPath headline

Story: Finding (rule in BUILD2 Phase G, threshold 30%).

Common advice and helpful advice differ for 76% of decisions. LiftPath advice: +2.9 points net lift. Collaborative filtering: +0.2.

## Real data (OULAD test students, goal: pass)

- LiftPath and collaborative filtering (user_cf) give different activities for 76.2% of 187,992 common test student-weeks. LiftPath and raw_success differ for 65.6%.
- Net lift (follower lift minus the random advice lift): LiftPath +2.9 pp (95% range +2.2 pp to +3.6 pp), user_cf +0.2 pp (95% range -0.5 pp to +0.8 pp), raw_success +1.9 pp.
- LiftPath gives an activity for 61.8% of test student-weeks. user_cf gives one for 97.9%. On the common subset, where all methods give an activity, the net lifts are +3.0 pp (LiftPath) and +0.1 pp (user_cf).
- LiftPath minus raw_success on the common subset: +0.3 pp (95% range -0.5 pp to +1.2 pp). For the pass goal, LiftPath does not beat raw_success there.

## Simulator (synthetic students with a known truth)

- Standard world: LiftPath minus no advice +15.8 pp in cohort 5 (+11.7 pp as the mean of cohorts 2 to 5). LiftPath minus collaborative filtering +10.5 pp (+6.2 pp mean). The best mean pass rate: popular.
- Hidden confounder world: LiftPath minus no advice +9.1 pp in cohort 5 (+6.2 pp as the mean of cohorts 2 to 5). LiftPath minus collaborative filtering +0.6 pp (-1.5 pp mean). The best mean pass rate: popular.
- Hidden confounder world, LiftPath + explore: minus no advice +16.8 pp in cohort 5 (+9.3 pp mean), minus greedy LiftPath +7.7 pp (+3.1 pp mean).
- popular has the best mean pass rate in both worlds. In this world the most used activity (quiz) is also the only one with a true effect, so popularity and help point the same way. On real data, popular has a lower net lift than LiftPath.
- The final cohort alone can mislead, because LiftPath + explore swings from cohort to cohort. Compare the means.
- The explore gain in the hidden confounder world depends on an upward bias of the explore estimate. The quiz range is above 0 only in the cohorts where the estimate is about 2 to 2.5 times the true effect. With a larger explore share (0.4), the estimates are near the truth, and LiftPath + explore does not move to quiz.

The data is observational. Lift is evidence, not proof of cause.
