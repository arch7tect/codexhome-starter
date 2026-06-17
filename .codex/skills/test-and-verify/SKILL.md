---
name: test-and-verify
description: Verify repository changes with appropriate commands, tests, linters, type checks, smoke checks, or manual inspection. Use after implementation, when debugging failures, or when the user asks whether a change works.
---

# Test And Verify

## Workflow

1. Read `AGENTS.md`.
2. Identify the smallest command that validates the changed behavior.
3. Prefer project-defined commands from config files or docs.
4. Use `uv run` for Python commands.
5. Run focused checks first, then broader checks if the change affects shared behavior.
6. If a check fails, capture the concrete failure and either fix it or report the blocker.
7. For local apps or frontends, verify the running app when practical.

## Output

Report:

- Commands run.
- Pass/fail result.
- Important failure lines or residual risks.
- Any checks that could not be run and why.

Do not claim success without an executed or clearly reasoned verification path.
