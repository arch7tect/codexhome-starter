---
name: starter-update
description: Update an existing CodexHome instance from the starter release. Use when the user asks to update, sync, upgrade, preview, or apply starter improvements to a populated CodexHome instance.
---

# Starter Update

Use this skill to apply starter-owned improvements while preserving instance-owned projects, sessions, incidents, wiki pages, and local context.

## Workflow

1. Read `AGENTS.md`.
2. Inspect `git status --short`. Stop if unrelated local changes would make the update unsafe.
3. Fetch starter tags and instance remotes when doing so will not overwrite local work.
4. Run a dry-run or check first when the user asked to preview.
5. Apply starter updates only from a release tag or pinned full commit.
6. Review changed files and conflicts.
7. Run manifest verification commands.
8. Commit the starter update as one reviewable change when the user asked to apply it.

## Commands

Preview current state:

```bash
uv run python scripts/sync_system.py --check
```

Preview a starter source:

```bash
uv run python scripts/sync_system.py --dry-run --from <starter-tag-or-commit>
```

Apply a starter source:

```bash
uv run python scripts/sync_system.py --apply --from <starter-tag-or-commit>
```

## Safety

- Do not use local path sources for normal instance updates.
- Do not overwrite user-owned paths.
- Treat conflicts as explicit user decisions.
- Do not rebase the populated instance onto starter history.
- Do not include `.env`, raw sessions, temporary files, or incident artifacts in the update commit.
