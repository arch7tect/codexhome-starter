# Projects

Use this directory for project profiles that share this Codex home.

Keep project code in its own repository. Store only coordination context here: paths, repository links, status, commands, conventions, related projects, and durable notes that help work across repositories.

A populated instance may keep a local project index in `projects/index.local.md`.

## Local Path Variables

Do not store developer-specific absolute home-directory paths in project profiles or skills. Use variables from local `.env` instead.

When running commands locally, resolve variables from each developer's shell environment. If a variable required by a project profile is missing, stop and ask the user where the local checkout or service lives instead of guessing a developer-specific path:

```bash
if [ -f ./.env ]; then
  set -a
  . ./.env
  set +a
elif [ -n "${CODEX_HOME:-}" ] && [ -f "$CODEX_HOME/.env" ]; then
  set -a
  . "$CODEX_HOME/.env"
  set +a
fi
```

New checkouts should copy `.env.template` to `.env` and keep `.env` local.

## Repository URL Fields

Project profiles should list both repository forms:

- `Repository SSH`: clone/push URL for developers with SSH access.
- `Repository Web`: browser URL for humans, reports, and issue references.

Use variables for instance-specific hosts or roots instead of hard-coding private hostnames and developer-local paths.

## Status Values

- `active`: current work may happen regularly.
- `paused`: relevant, but not currently worked on.
- `archived`: historical context only.

## Relationship Model

Projects may be independent or connected. Capture relationships in each project profile under `Related Projects`:

- `depends on`: this project needs another project or service to build, test, deploy, or run.
- `used by`: another project consumes this project.
- `shares context with`: projects have overlapping domain rules, clients, infrastructure, or operational notes.
- `supersedes` / `superseded by`: migration or replacement relationship.

When adding a new relationship, update both project profiles when both are tracked here.
