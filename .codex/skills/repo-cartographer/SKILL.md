---
name: repo-cartographer
description: Map an unfamiliar or changing repository before implementation. Use when Codex needs to understand project layout, modules, commands, tests, dependencies, runtime entrypoints, conventions, or ownership boundaries.
---

# Repo Cartographer

## Workflow

1. Read `AGENTS.md`.
2. Start with fast file discovery using `rg --files`.
3. Inspect build, dependency, test, lint, and runtime configuration.
4. Identify main modules, entrypoints, data flows, and test locations.
5. Prefer concrete file references over broad summaries.
6. Record reusable findings in `references/` only when they will help future sessions.

## Output

Return:

- Repository map.
- Important commands.
- Relevant conventions.
- Risky or unclear areas.
- Suggested next files to inspect for the current task.

Do not produce a full inventory when a targeted map is enough.
