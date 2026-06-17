---
name: code-reviewer
description: Review local or proposed changes for bugs, regressions, missing tests, security issues, maintainability risks, and mismatches with repository conventions. Use after implementation or when the user asks for review.
---

# Code Reviewer

## Workflow

1. Read `AGENTS.md`.
2. Inspect the diff and affected surrounding code.
3. Prioritize correctness, regressions, security, data loss, concurrency, error handling, and test coverage.
4. Check whether verification matches the risk of the change.
5. Avoid style-only comments unless they hide real maintenance risk.
6. Provide file and line references for findings when possible.

## Output

Lead with findings ordered by severity.

For each finding include:

- File reference.
- Risk.
- Concrete fix direction.

If there are no findings, say so and mention remaining test gaps or residual risk.
