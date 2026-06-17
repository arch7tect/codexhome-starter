# CodexHome

This repository stores shared Codex working memory: global instructions, reusable skills, project profiles, and long-lived references.

## Start Here

New users should read [Getting Started With CodexHome](references/getting-started-with-codexhome.md) after cloning the repository and creating `.env`.

Clean starter distribution and populated instance updates are described in [Starter And Instance Sync Plan](references/starter-instance-sync.md).

## Local Setup

Create a local `.env` from the committed template:

```bash
cp .env.template .env
```

Fill in developer-local paths:

```bash
CODEX_HOME=/path/to/CodexHome
PROJECTS_ROOT=/path/to/projects
```

`.env` is ignored by git and must not be committed. Keep only portable variable names and non-secret placeholders in `.env.template`.

Populated instances should complete any additional local setup documented in `README.local.md` when that file exists. Other instance-owned documents may also define variables for local project families.

## Project Profiles

Project profiles live in `projects/`. They use the variables from `.env` instead of developer-specific absolute paths.

Before running commands that depend on local paths, load the environment:

```bash
set -a
. ./.env
set +a
```

See `projects/README.md` for generic project profile rules. Populated instances may keep the active project index in `projects/index.local.md`.

See `references/README.md` for generic reference rules. Populated instances may keep a local reference index in `references/index.local.md`.
