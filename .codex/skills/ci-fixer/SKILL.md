---
name: ci-fixer
description: Diagnose and fix failing CI, test, lint, type-check, build, or workflow runs. Use when local checks fail, CI logs are available, or the user asks to debug failing checks.
---

# CI Fixer

## Workflow

1. Read `AGENTS.md`.
2. Gather the exact failing command, log, or check name.
3. Reproduce locally when practical.
4. Separate environment issues from code regressions.
5. Fix the smallest root cause.
6. Re-run the failing check.
7. If logs require network or external tools, request approval through the available command mechanism.

## Output

Report:

- Failing check.
- Root cause.
- Files changed.
- Verification command and result.
- Remaining CI risk.

Do not mask failures by weakening tests unless the user explicitly approves that direction.
