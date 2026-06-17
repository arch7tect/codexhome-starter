---
name: change-designer
description: Design a specific software change before editing code. Use for feature design, refactors, API changes, schema changes, behavior changes, migrations, or any implementation where contracts, edge cases, and verification strategy should be clarified first.
---

# Change Designer

## Workflow

1. Read `AGENTS.md` and task-relevant files.
2. Define the current behavior and target behavior.
3. Identify affected contracts: APIs, CLIs, schemas, storage, config, tests, and user-visible behavior.
4. Choose the smallest design that satisfies the target behavior.
5. List edge cases and compatibility risks.
6. Define validation before implementation.
7. Escalate to the user before destructive migrations, broad rewrites, or ambiguous product decisions.

## Output

Return:

- Current behavior.
- Target behavior.
- Proposed change design.
- Files likely to change.
- Edge cases.
- Verification plan.
- Approval gates, if any.
