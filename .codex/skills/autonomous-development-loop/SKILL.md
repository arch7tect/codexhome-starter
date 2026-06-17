---
name: autonomous-development-loop
description: Coordinate semi-autonomous engineering work across planning, implementation, verification, review, memory updates, and commit preparation. Use for complex tasks where Codex should work through multiple slices with minimal interruptions while stopping at explicit approval gates.
---

# Autonomous Development Loop

## Workflow

1. Read `AGENTS.md` and `references/semi-autonomous-engineering.md`.
2. Use `repo-cartographer` when repository structure is unclear.
3. Use `system-planner` for broad or multi-slice goals.
4. Use `change-designer` before risky or contract-affecting edits.
5. Use `implementation-runner` for one small slice at a time.
6. Use `test-and-verify` after each slice.
7. Use `code-reviewer` before declaring the work complete.
8. Use `memory-curator` when a durable decision or workflow should be recorded.
9. Use `commit-prep` only when the user asks to commit or the task explicitly includes committing.

## Autonomy Rules

- Continue without asking when the next step is local, reversible, and within the requested scope.
- Stop for approval at the gates listed in `references/semi-autonomous-engineering.md`.
- Keep each implementation slice small enough to verify.
- Prefer progress with clear residual risk over broad speculative rewrites.
- Report concise status during long work and final verification at completion.
