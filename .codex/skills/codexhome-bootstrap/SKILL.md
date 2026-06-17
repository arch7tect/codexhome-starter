---
name: codexhome-bootstrap
description: Initialize or configure a CodexHome instance. Use when the user says to initialize, bootstrap, set up, or configure a new CodexHome checkout, including setting PROJECTS_ROOT after bootstrap.
---

# CodexHome Bootstrap

Use this skill to turn a clean starter checkout into a local CodexHome instance.

## Workflow

1. Read `AGENTS.md`.
2. Confirm the current directory is the CodexHome checkout.
3. If the user provided a projects root before first initialization, run bootstrap with that value.
4. Otherwise run the standard bootstrap command.
5. If `PROJECTS_ROOT` remains a placeholder, ask the user for it. When they provide it after bootstrap, update only `.env`.
6. Report created scaffold files, `.env` status, and next user action.

## Commands

First initialization:

```bash
uv run python scripts/bootstrap_instance.py
```

First initialization with an explicit projects root:

```bash
uv run python scripts/bootstrap_instance.py --projects-root <path>
```

After bootstrap, update only local environment values:

```bash
uv run python scripts/bootstrap_instance.py --env-only --projects-root <path>
```

## Safety

- Do not infer `PROJECTS_ROOT`.
- Do not commit `.env`.
- Do not overwrite existing local scaffold files manually.
- If bootstrap reports a conflict or dirty-worktree blocker, stop and summarize it.
