---
name: system-planner
description: Plan complex software systems, large features, migrations, or multi-step engineering work before implementation. Use when the user asks for architecture, decomposition, execution strategy, risks, milestones, acceptance criteria, or a plan for a substantial change.
---

# System Planner

## Workflow

1. Read `AGENTS.md` and any relevant repository references.
2. Restate the goal in concrete engineering terms.
3. Identify constraints, unknowns, non-goals, and rollback needs.
4. Inspect the repository enough to avoid planning against imagined structure.
5. Break the work into small verifiable slices.
6. Define acceptance criteria for each slice.
7. Identify gates that require user approval before implementation.
8. Hand off scoped implementation slices to `implementation-runner` when the user wants execution.

## Output

Return:

- Goal summary.
- Assumptions and unknowns.
- Proposed architecture or approach.
- Ordered implementation slices.
- Verification plan.
- Approval gates.

Keep the plan practical and specific to the current repository.
