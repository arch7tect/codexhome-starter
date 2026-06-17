---
name: commit-prep
description: Prepare and create clean Git commits for CodexHome. Use when the user asks to commit, prepare staged changes, summarize a diff for commit, or ensure commit messages follow repository rules.
---

# Commit Prep

## Workflow

1. Read `AGENTS.md`.
2. Inspect `git status --short`.
3. Review staged and unstaged changes.
4. Stage only intended files unless the user asks for all current changes.
5. Use one-line commit messages.
6. Do not mention AI in commit messages.
7. Verify the final status and report the commit hash.

## Message Style

Use short imperative or descriptive messages, such as:

- `Add project skill workflow`
- `Update Python runtime`
- `Document repository conventions`

Do not use generated-by trailers or tool attribution.
