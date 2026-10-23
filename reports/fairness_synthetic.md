# Fairness (synthetic scope, goal: pass)

LiftPath results per group on test data. Coverage is the share of points where the status is not abstain. Recommend share is the share that gets an action. Follower lift has a 95% range from a student bootstrap. A group with fewer than 200 unique students is a small sample.

| attribute | group | students | points | coverage | recommend share | follower lift | 95% range | note |
|---|---|---|---|---|---|---|---|---|
| gender | F | 766 | 8,122 | 99.8% | 66.6% | +3.9 pp | +1.6 pp to +7.1 pp |  |
| gender | M | 734 | 7,749 | 99.7% | 67.1% | +2.9 pp | +0.4 pp to +5.5 pp |  |
| age_band | 0-35 | 486 | 5,135 | 99.7% | 66.7% | +4.7 pp | +1.5 pp to +7.6 pp |  |
| age_band | 35-55 | 555 | 5,882 | 99.7% | 66.7% | +4.6 pp | +1.6 pp to +7.7 pp |  |
| age_band | 55<= | 459 | 4,854 | 99.8% | 67.2% | +0.3 pp | -2.9 pp to +3.5 pp |  |
| imd_band | 0-10% | 126 | 1,329 | 99.7% | 66.9% | +1.1 pp | -5.3 pp to +6.8 pp | small sample |
| imd_band | 10-20 | 148 | 1,586 | 99.9% | 66.8% | +0.2 pp | -5.2 pp to +6.1 pp | small sample |
| imd_band | 20-30% | 173 | 1,820 | 99.8% | 66.9% | +5.7 pp | +0.4 pp to +10.6 pp | small sample |
| imd_band | 30-40% | 158 | 1,644 | 99.8% | 68.1% | +3.4 pp | -3.5 pp to +9.3 pp | small sample |
| imd_band | 40-50% | 147 | 1,539 | 99.6% | 68.3% | -0.6 pp | -5.2 pp to +5.8 pp | small sample |
| imd_band | 50-60% | 161 | 1,734 | 99.9% | 65.2% | +8.6 pp | +2.7 pp to +14.7 pp | small sample |
| imd_band | 60-70% | 128 | 1,354 | 99.9% | 67.6% | +6.0 pp | -0.9 pp to +11.3 pp | small sample |
| imd_band | 70-80% | 158 | 1,666 | 99.8% | 67.6% | +4.5 pp | -1.1 pp to +10.2 pp | small sample |
| imd_band | 80-90% | 143 | 1,516 | 99.3% | 64.1% | +5.4 pp | -1.3 pp to +10.6 pp | small sample |
| imd_band | 90-100% | 158 | 1,683 | 99.8% | 67.1% | -3.0 pp | -7.8 pp to +1.6 pp | small sample |
| disability | N | 764 | 8,101 | 99.8% | 66.8% | +2.3 pp | -0.1 pp to +4.8 pp |  |
| disability | Y | 736 | 7,770 | 99.7% | 67.0% | +4.3 pp | +1.4 pp to +6.6 pp |  |

All test points: follower lift +3.4 pp.
