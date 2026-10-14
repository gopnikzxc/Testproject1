# Team roster

Call each member with the Agent tool. This team ships as the `software-team` plugin, so the core members' `subagent_type` is the name below with the plugin prefix: `software-team:team-scout`, `software-team:team-architect`, and so on. Specialists added with `/software-team:team-hire` live in the project, so their `subagent_type` is the bare name from the table in `.team/roster-extra.md`. Every member has the team protocol preloaded, so they already know the workspace layout, report format and working rules.

## Core team

| Agent | Use for | Changes | Notes |
| --- | --- | --- | --- |
| `team-scout` | Building or refreshing `.team/project-profile.md` | profile only | Runs on a cheaper model; verifies commands |
| `team-architect` | Spec + plan for features, refactors, non-trivial bug fixes; plan revisions | `spec.md`, `plan.md` | Can read library docs on the web |
| `team-implementer` | Build mode: one plan task. Fix mode: review findings or tester bugs | source + tests | One task at a time; resume it for fixes to its own work |
| `team-tester` | Independent acceptance and edge-case tests from the spec | test files only | Never reuse an implementer for this |
| `team-reviewer` | Code review of a diff range; re-review after fixes | nothing (read-only) | Always runs in Phase 6 |
| `team-security` | Security review when flagged or the diff touches sensitive areas | nothing (read-only) | Runs in parallel with the reviewer |
| `team-debugger` | Diagnose mode for bug reports; fix mode when an implementer fails | tests (diagnose); source + tests (fix) | Leaves a regression test behind |
| `team-docs` | Docs for user- or developer-visible changes | docs, docstrings, changelog | Runs on a cheaper model |

## Routing rules

- A task flagged `[security-sensitive]` gets `team-security` in Phase 6, regardless of the diff heuristics.
- A task flagged `[migration]` or `[irreversible]` is shown individually at the approval gate, and its done-when must include a rollback or a dry run.
- An implementer gets at most one retry on the same failure; the next attempt goes to `team-debugger`, which brings a fresh, evidence-first view.

## Added specialists

Specialists added with `/software-team:team-hire` are listed in the project file `.team/roster-extra.md` (not here, because this plugin folder is replaced on every update). Read that file if it exists and apply its routing rules in addition to the ones above.
