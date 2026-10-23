# Evaluation (synthetic scope)

Train points: 15,688. Test points: 15,871 (1,500 students). Candidates: forumng, resource, glossary, oucontent, url, ouwiki, subpage, quiz.

Follower lift compares test students who did the recommended activity next week with students who did not, in the same level 0 cell and next-week effort band. The 95% range comes from a bootstrap that resamples students (200 runs). Coverage is the share of test points that get an action.

The random recommender also shows a positive follower lift, because engaged students do more of everything and pass more. This is the bias floor. Net lift subtracts it, with a paired bootstrap range. Net lift is the honest result.

Follower lift uses the same next-week effort bands as LiftPath. If an activity is driven by effort, both can rate it too high. The ground truth check on synthetic data (`eval_synthetic.md`) tests this against a known answer.

## Goal: pass

| recommender | coverage | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|---|
| random | 100.0% | +1.4 pp | +0.0 pp to +2.8 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | 99.9% | +4.9 pp | +3.3 pp to +6.3 pp | +3.5 pp | +1.5 pp to +5.4 pp |
| course_order | 100.0% | +4.1 pp | +2.6 pp to +5.5 pp | +2.7 pp | +0.9 pp to +4.7 pp |
| user_cf | 100.0% | +2.3 pp | +0.8 pp to +3.5 pp | +0.9 pp | -1.0 pp to +2.7 pp |
| raw_success | 99.7% | +3.7 pp | +2.2 pp to +5.3 pp | +2.3 pp | +0.3 pp to +4.5 pp |
| liftpath | 66.9% | +3.4 pp | +1.7 pp to +5.1 pp | +2.0 pp | -0.2 pp to +4.3 pp |

LiftPath status shares: recommend 66.9%, no_clear_winner 32.9%, abstain 0.3%. LiftPath gives an action only for recommend, so its coverage above is the recommend share.

### Common subset (10,612 test points where every recommender gives an action)

| recommender | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|
| random | +2.0 pp | +0.3 pp to +3.8 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | +4.0 pp | +2.2 pp to +5.7 pp | +2.0 pp | -0.5 pp to +4.2 pp |
| course_order | +4.0 pp | +2.1 pp to +5.9 pp | +2.0 pp | -0.5 pp to +4.6 pp |
| user_cf | +3.2 pp | +1.4 pp to +4.9 pp | +1.2 pp | -1.4 pp to +3.4 pp |
| raw_success | +4.8 pp | +3.1 pp to +7.1 pp | +2.8 pp | +0.1 pp to +5.4 pp |
| liftpath | +3.4 pp | +1.7 pp to +5.1 pp | +1.4 pp | -1.3 pp to +3.6 pp |

### LiftPath minus each recommender (paired bootstrap)

A range above zero means LiftPath has the higher follower lift.

| recommender | all test points | 95% range | common subset | 95% range |
|---|---|---|---|---|
| random | +2.0 pp | -0.2 pp to +4.3 pp | +1.4 pp | -1.3 pp to +3.6 pp |
| popular | -1.5 pp | -3.3 pp to +0.4 pp | -0.6 pp | -2.7 pp to +1.3 pp |
| course_order | -0.7 pp | -2.4 pp to +0.9 pp | -0.6 pp | -2.0 pp to +1.0 pp |
| user_cf | +1.1 pp | -0.8 pp to +3.0 pp | +0.2 pp | -2.1 pp to +2.3 pp |
| raw_success | -0.3 pp | -2.4 pp to +1.6 pp | -1.4 pp | -3.8 pp to +0.3 pp |

### Disagreement on the common subset

LiftPath and user_cf give different actions at 83.2% of the common test points. LiftPath and raw_success differ at 55.5%.

## Ground truth (synthetic data)

In the synthetic data, only quiz has a true effect on passing. forumng use rises with effort, but it has no effect. This table does not depend on follower lift.

| recommender | recommendations | share with a true effect (quiz) | share forumng |
|---|---|---|---|
| random | 15,871 | 12.2% | 12.5% |
| popular | 15,860 | 60.8% | 26.3% |
| course_order | 15,871 | 82.2% | 0.0% |
| user_cf | 15,871 | 19.9% | 9.3% |
| raw_success | 15,830 | 21.1% | 43.5% |
| liftpath | 10,612 | 63.0% | 0.0% |

In the generator, quiz is also a common activity: students use it in about 40% of their active weeks, at every effort level. The popular and course_order baselines pick quiz because many students use it, not because they measure its effect.

## Goal: distinction

| recommender | coverage | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|---|
| random | 100.0% | +2.6 pp | +1.6 pp to +3.6 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | 99.9% | +3.6 pp | +2.7 pp to +4.6 pp | +1.0 pp | +0.1 pp to +2.1 pp |
| course_order | 100.0% | +4.0 pp | +3.0 pp to +4.9 pp | +1.4 pp | +0.1 pp to +2.4 pp |
| user_cf | 100.0% | +2.9 pp | +2.0 pp to +3.8 pp | +0.3 pp | -1.0 pp to +1.2 pp |
| raw_success | 99.7% | +4.6 pp | +3.5 pp to +5.5 pp | +2.0 pp | +0.9 pp to +3.2 pp |
| liftpath | 57.6% | +7.1 pp | +5.4 pp to +9.0 pp | +4.5 pp | +2.7 pp to +6.4 pp |

LiftPath status shares: recommend 57.6%, no_clear_winner 42.2%, abstain 0.3%. LiftPath gives an action only for recommend, so its coverage above is the recommend share.

### Common subset (9,139 test points where every recommender gives an action)

| recommender | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|
| random | +4.0 pp | +2.3 pp to +5.6 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | +5.7 pp | +4.1 pp to +7.3 pp | +1.6 pp | +0.0 pp to +3.4 pp |
| course_order | +6.1 pp | +4.6 pp to +7.7 pp | +2.1 pp | +0.1 pp to +3.9 pp |
| user_cf | +4.3 pp | +2.9 pp to +5.8 pp | +0.3 pp | -1.6 pp to +2.1 pp |
| raw_success | +7.4 pp | +5.9 pp to +9.1 pp | +3.4 pp | +1.6 pp to +5.3 pp |
| liftpath | +7.1 pp | +5.4 pp to +9.0 pp | +3.1 pp | +1.0 pp to +5.3 pp |

### LiftPath minus each recommender (paired bootstrap)

A range above zero means LiftPath has the higher follower lift.

| recommender | all test points | 95% range | common subset | 95% range |
|---|---|---|---|---|
| random | +4.5 pp | +2.7 pp to +6.4 pp | +3.1 pp | +1.0 pp to +5.3 pp |
| popular | +3.5 pp | +1.7 pp to +5.3 pp | +1.4 pp | -0.5 pp to +3.2 pp |
| course_order | +3.1 pp | +1.7 pp to +4.7 pp | +1.0 pp | -0.4 pp to +2.5 pp |
| user_cf | +4.2 pp | +2.6 pp to +6.1 pp | +2.8 pp | +0.7 pp to +4.9 pp |
| raw_success | +2.5 pp | +1.2 pp to +4.2 pp | -0.3 pp | -1.8 pp to +1.4 pp |

### Disagreement on the common subset

LiftPath and user_cf give different actions at 85.5% of the common test points. LiftPath and raw_success differ at 47.7%.

## Gate 3

LiftPath coverage (status is not abstain) for the pass goal: 99.7%. The gate needs 50%. Result: PASS (the gate counts only on full data).

## Figures

- `figures/eval_lift_synthetic.png`
- `figures/fairness_synthetic.png`
- `figures/synthetic_truth.png`
