---
name: team-retro
description: Retrospective for the /team agents. Reads recent task logs, reports and lessons, finds recurring problems, and proposes small evidence-backed edits to the agent prompts so those problems stop recurring.
argument-hint: "[number of recent tasks to review, default 5]"
disable-model-invocation: true
---

# /team-retro — improve the team from evidence

You are running a retrospective on the software team in this repository. The goal is to turn what went wrong (or slowly) in recent runs into specific improvements to the prompts that govern the team, so the same problem doesn't happen again. You change prompts only with the user's approval.

Number of tasks to review: $ARGUMENTS (default 5 if empty).

## Steps

1. **Gather evidence.** List `.team/tasks/` and take the most recent N task directories. For each, read `state.md`, `log.md`, `summary.md` if present, and skim the reports — especially review findings, tester bug reports, `FAILED` and `BLOCKED` reports, and escalations. Also read `.team/lessons.md` and `.team/retros.md` if it exists (so you don't re-propose changes already made).

2. **Find patterns.** Count occurrences across tasks. Look for:
   - the same kind of review finding appearing repeatedly → the implementer's quality bar is missing a check;
   - bugs the tester found that the reviewer missed, or the reverse → a gap in one of their checklists;
   - `BLOCKED` reports for the same reason → the delegation template or plan template is missing information;
   - tasks needing more than one fix round, or debugger escalations → the plan's task sizing or done-when checks are weak;
   - escalations to the user that the spec could have prevented → the architect's open-questions step needs strengthening;
   - wasted work: agents redoing discovery the profile should have covered → the scout's profile is missing something.

   Act on a pattern seen in at least two tasks, or on a single severe incident (a defect that reached the final summary, data at risk, a destructive action attempted).

3. **Diagnose.** For each pattern, identify the one place in the prompts where a change would have prevented it: a specific section of a file in `.claude/agents/team/`, `.claude/skills/team/SKILL.md`, `.claude/skills/team-protocol/SKILL.md`, or the profile template in `team-scout.md`.

4. **Propose at most five changes.** For each:
   - **Evidence:** the task IDs and report excerpts (short) that show the pattern.
   - **Change:** the exact text to add, replace or delete, shown as a small diff.
   - **Expected effect:** what should happen differently next time.

   Prefer adding a concrete, checkable item to a checklist or quality bar over adding general advice. Prefer editing an existing line over adding a new one; prompts that only grow get worse. Look for things to remove, too: rules nobody needed, and lessons in `.team/lessons.md` that are now encoded in a prompt (remove them from lessons when the prompt change is applied).

5. **Ask the user** which proposals to apply (AskUserQuestion, multi-select). Apply only those.

6. **Record the retro.** Append to `.team/retros.md`: the date, the tasks reviewed, the patterns found, and the changes applied or declined with reasons. Next time, check whether the applied changes worked.
