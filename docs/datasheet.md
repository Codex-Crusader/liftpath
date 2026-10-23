# LiftPath datasheet

## Source

- Name: Open University Learning Analytics Dataset (OULAD).
- Publisher: The Open University, United Kingdom.
- License: CC BY 4.0. You can share and adapt the data if you give credit.
- Citation: Kuzilek J., Hlosta M., Zdrahal Z. "Open University Learning Analytics dataset." Scientific Data 4, article 170171, 2017. DOI 10.1038/sdata.2017.171 (verify the article number and DOI).
- Download: `make data` tries the Open University URL first, then the UCI Machine Learning Repository copy (46.7 MB zip). The UCI copy is the one that worked in this build. If the 7 CSV files are already in `data/raw/`, the script skips the download.

## Contents

| table | rows (canonical) |
|---|---|
| courses (module presentations) | 22 |
| enrollments (students per presentation) | 32,593 |
| items (learning resources) | 6,364 |
| events (daily clicks per student and item) | 10,655,280 |
| assessments | 206 |
| submissions | 173,912 |

7 modules (AAA to GGG), presentations 2013B, 2013J, 2014B and 2014J. Demographics: gender, region, highest education, deprivation band (imd_band), age band, previous attempts, credits and disability. Outcomes: Pass, Distinction, Fail and Withdrawn.

## Preprocessing

- `src/liftpath/adapters/oulad.py` reads the 7 CSV files into canonical Parquet tables. "?" and empty values become NULL. The adapter stops if a join changes a row count, if a student key repeats, or if an outcome or assessment type is unknown.
- 11 exam rows have no date. Their due day is the course length.
- 45 enrollments have no registration day.
- Days are relative to the presentation start and can be negative. Clicks before day 0 count only in the cumulative activity shares.
- Decision points: one row per registered student per week, from week 0 to the second-to-last week. Full data: 898,212 points (587,671 train, 310,541 test).
- Split: per module, the latest presentation (2014J) is test. All earlier presentations are train.
- Candidate activity types: the 8 types with the most training clicks, without the course homepage.
- Recovery points: 6,159 (3,892 train, 2,267 test).

## Synthetic data

`make synthetic` writes a synthetic scope with the same tables and a known truth (`SPEC.md` section 16). The simulator uses the same rules with a second world that has a hidden confounder. The synthetic data contains no real person.

## Privacy

- OULAD student ids are pseudonymous. LiftPath adds no other identifier.
- `data/raw/` and `data/processed/` stay out of git. Only `data/app/` is committed.
- In `data/app/`, every count below 5 is NULL with a `suppressed` flag. Rates that come from a suppressed count are NULL too. The app shows such a count as "fewer than 5".
- `data/app/` holds no final result of any student and no activity flags of test students. The route lookup tables hold rates, not counts. The item schedule keeps only items with 5 or more clicks.
- The demo mode database (`data/live/`) is local, out of git, and resets when the app starts.

## Known issues

- Scores count from the later of the submit day and the due day. Real marking takes longer.
- Most week_from and week_to values of items are missing. An item's active day is then the click-weighted median click day.
- Activity types are coarse. Some activities are not open every week.
- The data comes from one university in 2013 and 2014.
