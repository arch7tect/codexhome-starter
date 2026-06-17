---
name: implementation-runner
description: Implement a scoped engineering slice in the repository. Use when the plan or user request is specific enough to edit code, scripts, docs, skills, or configuration, and Codex should make the change end to end.
---

# Implementation Runner

## Workflow

1. Read `AGENTS.md`.
2. Confirm the requested slice and avoid unrelated refactors.
3. Inspect nearby code before editing.
4. Use existing project patterns and dependencies.
5. For scripts, use Python and manage dependencies with `uv`.
6. Edit files with `apply_patch` for manual changes.
7. Keep comments minimal and explain only how or why.
8. Run the smallest meaningful verification, then broader checks when risk justifies it.
9. Hand off to `test-and-verify` or `code-reviewer` after implementation.

## Guardrails

- Do not touch unrelated dirty worktree changes.
- Do not perform destructive operations without explicit approval.
- Do not invent abstractions unless they remove real complexity or match local patterns.
- Stop at approval gates listed in `references/semi-autonomous-engineering.md`.
