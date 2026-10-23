# Evaluation (full scope)

Train points: 587,671. Test points: 310,541 (10,203 students). Candidates: oucontent, forumng, quiz, subpage, resource, ouwiki, url, glossary.

Follower lift compares test students who did the recommended activity next week with students who did not, in the same level 0 cell and next-week effort band. The 95% range comes from a bootstrap that resamples students (200 runs). Coverage is the share of test points that get an action.

The random recommender also shows a positive follower lift, because engaged students do more of everything and pass more. This is the bias floor. Net lift subtracts it, with a paired bootstrap range. Net lift is the honest result.

Follower lift uses the same next-week effort bands as LiftPath. If an activity is driven by effort, both can rate it too high. The ground truth check on synthetic data (`eval_synthetic.md`) tests this against a known answer.

## Goal: pass

| recommender | coverage | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|---|
| random | 100.0% | +0.3 pp | -0.0 pp to +0.7 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | 100.0% | +1.6 pp | +1.0 pp to +2.3 pp | +1.3 pp | +0.6 pp to +2.0 pp |
| course_order | 97.9% | +2.2 pp | +1.5 pp to +2.8 pp | +1.8 pp | +1.1 pp to +2.6 pp |
| user_cf | 97.9% | +0.5 pp | -0.1 pp to +1.1 pp | +0.2 pp | -0.5 pp to +0.8 pp |
| raw_success | 100.0% | +2.2 pp | +1.6 pp to +2.9 pp | +1.9 pp | +1.3 pp to +2.6 pp |
| liftpath | 61.8% | +3.3 pp | +2.5 pp to +4.0 pp | +2.9 pp | +2.2 pp to +3.6 pp |

LiftPath status shares: recommend 61.8%, no_clear_winner 38.2%, abstain 0.0%. LiftPath gives an action only for recommend, so its coverage above is the recommend share.

### Common subset (187,992 test points where every recommender gives an action)

| recommender | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|
| random | +0.3 pp | -0.1 pp to +0.9 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | +2.1 pp | +1.4 pp to +2.9 pp | +1.8 pp | +0.9 pp to +2.6 pp |
| course_order | +2.4 pp | +1.7 pp to +3.4 pp | +2.1 pp | +1.3 pp to +2.9 pp |
| user_cf | +0.4 pp | -0.3 pp to +1.1 pp | +0.1 pp | -0.7 pp to +0.8 pp |
| raw_success | +3.0 pp | +2.0 pp to +3.9 pp | +2.7 pp | +1.7 pp to +3.6 pp |
| liftpath | +3.3 pp | +2.5 pp to +4.0 pp | +3.0 pp | +2.3 pp to +3.7 pp |

## Goal: distinction

| recommender | coverage | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|---|
| random | 100.0% | +0.1 pp | -0.3 pp to +0.4 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | 100.0% | +1.1 pp | +0.5 pp to +1.7 pp | +1.0 pp | +0.4 pp to +1.7 pp |
| course_order | 97.9% | +1.7 pp | +1.0 pp to +2.3 pp | +1.6 pp | +1.0 pp to +2.3 pp |
| user_cf | 97.9% | +1.1 pp | +0.5 pp to +1.8 pp | +1.0 pp | +0.4 pp to +1.6 pp |
| raw_success | 100.0% | +3.1 pp | +2.2 pp to +4.2 pp | +3.0 pp | +2.1 pp to +4.3 pp |
| liftpath | 54.3% | +5.9 pp | +4.7 pp to +7.1 pp | +5.9 pp | +4.6 pp to +7.0 pp |

LiftPath status shares: recommend 54.3%, no_clear_winner 45.7%, abstain 0.0%. LiftPath gives an action only for recommend, so its coverage above is the recommend share.

### Common subset (167,438 test points where every recommender gives an action)

| recommender | follower lift | 95% range | net lift | 95% range |
|---|---|---|---|---|
| random | -0.0 pp | -0.5 pp to +0.5 pp | +0.0 pp | +0.0 pp to +0.0 pp |
| popular | +1.2 pp | +0.4 pp to +2.0 pp | +1.3 pp | +0.3 pp to +2.2 pp |
| course_order | +1.7 pp | +0.7 pp to +2.5 pp | +1.7 pp | +0.7 pp to +2.6 pp |
| user_cf | +1.5 pp | +0.7 pp to +2.3 pp | +1.5 pp | +0.6 pp to +2.3 pp |
| raw_success | +4.0 pp | +2.7 pp to +5.5 pp | +4.0 pp | +2.7 pp to +5.7 pp |
| liftpath | +5.9 pp | +4.7 pp to +7.0 pp | +5.9 pp | +4.6 pp to +7.1 pp |

## Gate 3

LiftPath coverage (status is not abstain) for the pass goal: 100.0%. The gate needs 50%. Result: PASS.

## Figures

- `figures/eval_lift.png`
- `figures/fairness.png`
