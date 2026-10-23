# LiftPath demo script (3 minutes)

Before you record:

1. Run `make app` and open http://localhost:8501 in a browser window of 1600 x 900 or larger.
2. Restart the app before each take, because demo mode keeps its data until a restart.
3. Make sure that `data/live/teacher_settings.json` does not exist, so the teacher view opens with the default settings.
4. Keep the "Teacher view" tab open at the start. Do not start on a chart.

The clicks and the results below come from an AppTest run on the committed `data/app/` (`tests/test_app.py::test_demo_script_clicks`). The spoken text has about 340 words, which leaves time for the clicks.

## 0:00 to 0:35, Teacher view: the class

Screen: the "Teacher view" tab, as the app opens. Course FFF (2014J), week 19, goal Pass. The top card reads "100 of 104 students with a suggestion get different advice from LiftPath than from the usual rule".

Say: "Most study advice says: do what students like you did. LiftPath asks: what helped students like you? It compares students in the same situation who studied about as much. In this class, the two answers differ for 100 of 104 students."

Screen: the student panel on the right shows student 582266, "Go back first": go back to the earlier quizzes, then the external links, with a message to copy.

Say: "For each student, the teacher gets one next step, the reason in plain words, and a message to send. The numbers stay behind "Show the evidence"."

## 0:35 to 1:05, Your route: one student

Clicks:

1. Click the "Your route" tab.
2. Click the "Module" box and select GGG.
3. Click the "Student" box, type 388259, and press Enter. The box shows "388259 (GGG_2014J)".
4. Click the "Week" box and select 31.

Screen: the card "First, go back: quizzes (score 10 on the last assessment)", then four week cards: week 31 "course pages" (lift +7.6 pp, 95% range +0.2 pp to +15.0 pp), and weeks 32 to 34 "files" (lift +3.8 pp).

Say: "This student scored 10 on the last assessment. First, go back to earlier quizzes: 44% of similar students who did that passed the next assessment, against 34%. Then the route plans four weeks. Each step has a lift and a 95% range above zero."

5. Scroll down to the chart "Projected chance of pass".

Say: "The route projects 93.5% against 91.4% for the typical path. This is a projection from past students, not a guarantee."

## 1:05 to 1:30, Your route: the trap and the evidence

Screen: the section "What common advice says".

Say: "Here, common advice agrees with LiftPath on course pages. On the test student-weeks where every method gives an activity, it disagrees 76% of the time."

6. Click "Why?" to open it.

Screen: the bar chart of lifts and the table "Check one activity by hand".

Say: "Every number has its counts. A teacher can compute the lift by hand from this table."

## 1:30 to 2:05, Simulator

7. Click the "Simulator" tab.
8. Click the "World" box and select "hidden confounder world".

Screen: the pass rate chart by cohort and the table of means.

Say: "In the simulator we know the truth: only quizzes help. In the hidden confounder world, able students also use files, which do nothing. Greedy LiftPath is pulled toward files. LiftPath plus explore tries random advice 20% of the time, which gives an experiment. Its estimate sits above the true effect, so we show the means too."

## 2:05 to 2:35, Try it

9. Click the "Try it" tab.
10. In "New student id", type demo1. In "Module", select GGG. Click "Add student".
11. In "Week", select 3.
12. In the "Log activity" box, select "quizzes" in "Activity", type 40 in "Clicks", and click "Log activity".
13. Click "Get advice for next week".

Screen: "Next step: discussion forum", state "early weeks, score none, effort high", lift +8% (95% range +2% to +13%).

Say: "A new student logs 40 quiz clicks in week 3. LiftPath gives advice with its range and logs it. When students get a final result, a refresh adds them to the evidence. Data resets on restart."

## 2:35 to 2:50, Rescue map

14. Click the "Rescue map" tab.

Say: "After a low score, which earlier material helped? In CCC, two edges have ranges above zero. A shuffle test says they can be chance, and we say so."

## 2:50 to 3:00, Evidence and close

15. Click the "Evidence" tab.

Screen: the four result tiles at the top of the tab.

Say: "On 10,203 test students, LiftPath advice has a net lift of +2.9 points. Similar-students advice has +0.2. LiftPath supports decisions. It does not make them."
