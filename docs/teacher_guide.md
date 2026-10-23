# LiftPath teacher guide

This page tells you how to use the "Teacher view" tab. You do not need to know statistics.

## What LiftPath gives you

For each student in your course, LiftPath gives one next study activity and the reason in plain words. The reason comes from past students who were in the same position and studied about as much. LiftPath does not tell you what the student must do. You decide.

The usual advice is "do what similar students did". LiftPath gives "do what helped similar students". The card at the top of the page tells you for how many of your students the two answers are different.

## Open your class

1. In "Course", select your course.
2. In "Week of the course", select the current week.
3. In "Goal", select Pass or Distinction.

The four boxes below the card count your students in each group. Click a group name under "Show" to see only those students.

| Group | Meaning | What you can do |
|---|---|---|
| Go back first | The student got a low mark on the last assessment. Going back to earlier material helped similar students pass the next one. | Send the message. Suggest the earlier material first. |
| No recent activity | The student did not click in the course for 2 weeks or more. | Contact the student before you give study advice. |
| Next step suggested | One activity clearly helped similar students. | Send the message if you agree. |
| No change suggested | No activity helped clearly more. | No action is necessary. |

The list puts students with a low mark first, then students with no recent activity. These are facts from the course log. LiftPath does not predict who will fail.

## Open one student

Click a row in the list, or select the student in "Open a student". The panel on the right shows:

- the facts: the average mark band, the activity this week and the last assessment mark;
- "What to suggest": one to three numbered steps, each with its reason;
- a plan for the next 4 weeks;
- a message for the student. To copy it, click the copy icon at the top right of the message box.

"Show the evidence" opens the numbers behind each step. The "Your route" tab has the full comparison table for each activity.

## Download the list

Click "Download this list (CSV)". The file has one row for each student in the current list, with the group, the suggestion and the message. You can open it in a spreadsheet or use it for a mail merge.

## Change your settings

Open the "Settings" tab. Under "Your preferences" you can:

- select the course and the goal that open first;
- set after how many weeks without clicks a student goes to "No recent activity";
- turn on "Show percentages" to add percentages to the suggestions in the list and the download;
- write the names that your students see for each activity type, for example "Weekly quiz" for "quizzes";
- write your own message. `$suggestion` is replaced with the suggestion for the student, and `$student` with the student ID.

Click "Save settings". The teacher view uses the new settings immediately.

The "Course rules" and "Fixed rules" tables show the settings that only an administrator can change. The steps are in `docs/admin_guide.md`.

## Limits

- The data is observational. A suggestion is evidence, not proof that the activity causes success.
- A plan projection comes from past students. It is not a guarantee.
- The settings are shared by everyone who uses the same app. This version has no login.
