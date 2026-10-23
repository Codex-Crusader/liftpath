# LiftPath administrator guide

This page tells you how to set up LiftPath for your own courses, and which settings you can change. The exact rules are in `SPEC.md`.

## Three levels of settings

| Level | Who changes it | Where | After a change |
|---|---|---|---|
| Teacher preferences | Each teacher | The "Settings" tab in the app | No action. The app uses them at once. |
| Course rules | The administrator | `config.yaml` | Run `make all` and deploy `data/app/`. Some rules need only a restart. The "Settings" tab tells you which. |
| Fixed rules | Nobody, without a new evaluation | `config.yaml` | Run `make all`, read `reports/eval.md` again, and update the docs. |

Teacher preferences are saved in `data/live/teacher_settings.json` (the key `teacher_settings_path` in `config.yaml`). The app reads this file at each page load. If the file has a value that is not valid, the app uses the default value and shows a warning.

The fixed rules are `min_count`, `prior_strength`, `z` and `display_min_count`. The evaluation results depend on the first three. `display_min_count` is the privacy floor: the app and `data/app/` never show a count below it. Do not lower it.

## Set up LiftPath for your own data

1. Export your learning platform data as the six tables of the canonical schema in `SPEC.md` section 3: courses, enrollments, items, events, assessments and submissions.
2. Write an adapter that writes these tables as Parquet files to `data/processed/<scope>/canonical/`. Use `src/liftpath/adapters/oulad.py` as the example. The adapter maps your activity types to `item_type`, and your marks to a score from 0 to 100.
3. Add a label for each new activity type to `LABELS` in `src/liftpath/recommend.py`. Teachers can also set their own names in the "Settings" tab.
4. Edit the course rules in `config.yaml`, for example `low_score`, `exclude_types` and `n_candidates`.
5. Run `make all`. The command builds the states, the lift tables, the evaluation, the routes, the rescue map, the simulator and the app data.
6. Read `reports/eval.md`. If LiftPath advice does not show a net lift above zero on your test students, do not give the advice to teachers.
7. Copy `data/app/` and `reports/headline.json` to the server, and start the app with `make app`.

The app reads only `config.yaml`, `data/app/`, `data/live/` and `reports/headline.json`. It never reads `data/raw/` or `data/processed/`. Only `data/app/` holds student data on the server, and it has no names and no counts below `display_min_count`.

## Keep the data current

To add a new week of data, export the tables again and run `make all`. The build takes about 5 minutes on the full OULAD data on a laptop. A student state at week w uses only data up to the end of week w.

## Limits of this version

- There is no login. All teachers on one server share one settings file.
- Teacher preferences change only what the teacher view shows. They do not change how LiftPath finds a suggestion.
- The app shows student IDs, not names. To show names, join the downloaded list with your own student register.
