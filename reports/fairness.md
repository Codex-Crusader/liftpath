# Fairness (full scope, goal: pass)

LiftPath results per group on test data. Coverage is the share of points where the status is not abstain. Recommend share is the share that gets an action. Follower lift has a 95% range from a student bootstrap. A group with fewer than 200 unique students is a small sample.

| attribute | group | students | points | coverage | recommend share | follower lift | 95% range | note |
|---|---|---|---|---|---|---|---|---|
| gender | F | 4,252 | 131,151 | 100.0% | 59.5% | +3.8 pp | +2.5 pp to +4.9 pp |  |
| gender | M | 5,951 | 179,390 | 100.0% | 63.5% | +2.9 pp | +2.0 pp to +3.6 pp |  |
| age_band | 0-35 | 7,101 | 212,574 | 100.0% | 63.1% | +3.6 pp | +2.8 pp to +4.4 pp |  |
| age_band | 35-55 | 3,011 | 95,039 | 100.0% | 59.4% | +2.7 pp | +1.4 pp to +4.0 pp |  |
| age_band | 55<= | 91 | 2,928 | 100.0% | 49.1% | +2.2 pp | -3.6 pp to +8.8 pp | small sample |
| imd_band | 0-10% | 967 | 27,118 | 100.0% | 63.7% | +4.7 pp | +1.9 pp to +6.8 pp |  |
| imd_band | 10-20 | 1,054 | 30,242 | 100.0% | 62.1% | +4.9 pp | +2.5 pp to +7.2 pp |  |
| imd_band | 20-30% | 1,124 | 32,374 | 100.0% | 61.4% | +3.6 pp | +1.6 pp to +5.3 pp |  |
| imd_band | 30-40% | 1,096 | 32,937 | 100.0% | 60.9% | +1.9 pp | -0.4 pp to +4.1 pp |  |
| imd_band | 40-50% | 1,030 | 30,893 | 100.0% | 61.7% | +2.6 pp | +0.3 pp to +4.8 pp |  |
| imd_band | 50-60% | 998 | 31,146 | 100.0% | 62.4% | +5.3 pp | +2.7 pp to +7.3 pp |  |
| imd_band | 60-70% | 968 | 30,173 | 100.0% | 61.0% | +2.4 pp | +0.2 pp to +4.6 pp |  |
| imd_band | 70-80% | 929 | 29,900 | 100.0% | 60.5% | +4.6 pp | +2.8 pp to +6.7 pp |  |
| imd_band | 80-90% | 869 | 27,651 | 100.0% | 61.6% | +2.7 pp | +0.3 pp to +5.6 pp |  |
| imd_band | 90-100% | 794 | 25,411 | 100.0% | 61.9% | +2.1 pp | -0.0 pp to +4.0 pp |  |
| imd_band | unknown | 374 | 12,696 | 100.0% | 63.8% | -0.9 pp | -3.2 pp to +1.7 pp |  |
| disability | N | 9,251 | 283,190 | 100.0% | 61.8% | +3.1 pp | +2.2 pp to +3.8 pp |  |
| disability | Y | 952 | 27,351 | 100.0% | 61.4% | +5.2 pp | +2.7 pp to +7.8 pp |  |

All test points: follower lift +3.3 pp.
