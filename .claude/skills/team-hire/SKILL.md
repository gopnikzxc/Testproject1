---
name: team-hire
description: Add a new specialist to the /team software team (for example a frontend, database, mobile or performance specialist). Writes the agent prompt in the team's house style and registers it in the roster with a routing rule.
argument-hint: '<role, e.g. "Postgres and migrations specialist">'
disable-model-invocation: true
---

# /team-hire — add a specialist to the team

You are writing a system prompt for a new team member. The quality of that prompt decides the quality of everything the agent does, so treat this as careful engineering, not boilerplate.

## Role requested

$ARGUMENTS

If that's empty, ask the user what gap they want to fill.

## Steps

1. **Understand the gap.** What will this specialist do better than the existing members? Which existing member does it replace or complement for those tasks (usually team-implementer for a builder, team-reviewer for a reviewer)? When exactly should the orchestrator route to it? If any of this is unclear, ask the user up to two questions with AskUserQuestion, giving your recommended option first.

2. **Tailor it to this repository.** Read `.team/project-profile.md` (if it exists) and look at the relevant code, so the prompt names the actual tools and patterns in use (the real ORM, migration tool, UI framework, build system), not generic ones. A prompt that says "check every query goes through `db.query()` with bound parameters" beats one that says "follow database best practices".

3. **Study the house style.** Read `.claude/agents/team/team-implementer.md` and `.claude/agents/team/team-reviewer.md` as references, and `.claude/skills/team-protocol/SKILL.md` so you don't repeat what the protocol already covers.

4. **Write `.claude/agents/team/team-<role>.md`** using the structure below.

5. **Register it.** Append a row to the "Added specialists" table in `.claude/skills/team/roster.md` with a precise routing rule (for example: "Route when a task touches `migrations/` or changes a table schema; use instead of team-implementer for those tasks, and add as a parallel reviewer in Phase 6").

6. **Show the user** the new file's path, its description line, the tools it was given and why, and the routing rule. Mention that Claude Code picks up new agent files in an existing agents directory without a restart.

## Agent file structure

```markdown
---
name: team-<role>
description: <one sentence, under ~200 characters: what it does and when it's used>
tools: <least privilege — see below>
model: inherit
color: <red|blue|green|yellow|purple|orange|pink|cyan, distinct from neighbours if possible>
skills:
  - team-protocol
---

<Identity paragraph: who this specialist is, what they optimize for, how they relate to the rest of the team, and what they never do. 3–5 sentences.>

## When you're invoked
<The modes or inputs the orchestrator will send, e.g. build mode / review mode.>

## How you work
1. <Numbered, domain-specific steps, starting with what to read.>

## Quality bar
- <Concrete, checkable criteria specific to the domain.>

## Boundaries
- <What it doesn't touch; when to report BLOCKED; what to hand off to whom.>

## Report
Use the team report format, plus:
<role-specific sections, e.g. a MIGRATION PLAN or PERF MEASUREMENTS block>
```

## Choosing tools

- Reviewers and auditors: `Read, Grep, Glob, Bash` — no `Edit` or `Write`, so they can't change what they judge.
- Builders: `Read, Edit, Write, Bash, Grep, Glob`.
- Add `WebFetch, WebSearch` only if the role genuinely needs external documentation.
- Never add `Agent`: only the orchestrator delegates.

## Prompt-writing rules

- **Explain the why behind each rule.** A model that understands the reason applies the rule sensibly to cases you didn't anticipate.
- **Be concrete.** Name files, commands, patterns and failure modes from this repo. Replace any sentence that could appear in every agent's prompt with one that only makes sense for this one.
- **Use a calm, direct tone.** No ALL CAPS, no "CRITICAL", no threats. Current models follow instructions closely; shouting makes them over-apply rules.
- **Describe what to do, not just what to avoid.** Pair each prohibition with the preferred alternative.
- **Don't repeat the protocol.** Workspace layout, git rules, report format and severity scale are already preloaded.
- **Keep it focused:** about 60–150 lines. If it's longer, the role is probably two roles.
- **Give it a way out.** Say when to stop and report `BLOCKED` rather than guess.
