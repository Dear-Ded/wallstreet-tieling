# Requirement Intake And Planning

This project is driven by product-language requests. The maintainer often gives
abstract, non-technical, fast-changing requirements in one long-running
conversation. Agents must translate that input into product plans, engineering
lanes, tests, and release gates.

## Operating Assumption

The user owns product direction but is not expected to provide technical field
names, module names, schemas, branch strategy, or implementation details.

Agent responsibility:

- Restate the business goal in concrete product language.
- Identify what is in scope for the current release track.
- Split the work into implementation lanes.
- Name the files likely to change.
- Name the verification commands.
- Update the project board when priority, scope, or delivery status changes.
- Ask only when the product intent is genuinely ambiguous or irreversible.

## Intake Flow

When a new request arrives:

1. Capture the business intent in one sentence.
2. Classify it into a lane: runtime, agent delivery, report output, source
   admission, public release, product design, or local hygiene.
3. Decide whether it is P0, P1, P2, or future-only.
4. Check `PROJECT_TASKBOARD.md` and `docs/PROJECT_MAP.md` for conflicts.
5. Create or reuse a narrow branch/worktree when the change is substantial.
6. Implement only the lane that was selected.
7. Run focused tests first; run release gates when release surfaces change.
8. Record status in `PROJECT_TASKBOARD.md` or the relevant release document.

## Priority Rules

| Priority | Meaning | Examples |
| --- | --- | --- |
| P0 | Blocks current desktop-agent delivery or public release trust | broken CLI/API/MCP, privacy leak, package breakage, report artifact loss |
| P1 | Improves current product usefulness without changing release target | stronger source resilience, better graph handoff, richer report sections |
| P2 | Useful polish or operator convenience | docs, examples, small UX improvements |
| Future | Important but not part of current release track | app, mini-program, hosted SaaS, full public web workbench |

## Planning Template

Use this template in project notes or taskboard entries:

```text
Goal:
Lane:
Priority:
User-facing outcome:
Files likely to change:
Out of scope:
Verification:
Rollback/cleanup notes:
```

## Conversation Discipline

- Do not treat every new user message as a reason to abandon the active lane.
- If the new request is a clarification, fold it into the current lane.
- If it is a new lane, record it as next work unless it is P0.
- If it conflicts with release safety, preserve the release gate and explain the
  tradeoff in product language.
- Do not ask the user to provide technical implementation details; infer them
  from the repository and public docs.

## Examples

Abstract request:

> Make the investigation deeper and more automatic.

Agent translation:

- Lane: runtime + source admission.
- Outcome: one-click investigation should expose source-health recovery,
  related-subject traversal, relationship graph, and report artifact handoff.
- Verification: investigation tests, API smoke, MCP smoke, host smoke.

Abstract request:

> The workspace is too messy; put it on track.

Agent translation:

- Lane: local hygiene + project management.
- Outcome: clean main worktree, remove clean stale worktrees, keep dirty
  auxiliary worktrees for review, document branch/worktree/verification policy.
- Verification: `git status`, `git worktree list`, release hygiene checks.
