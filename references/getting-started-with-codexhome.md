# Getting Started With CodexHome

This guide describes the intended user journey from a clean checkout to useful repository memory.

CodexHome is not a project repository. It is the local operating context for agent-assisted work: global rules, skills, project profiles, references, and the LLM wiki lifecycle.

## Mental Model

Keep system mechanics separate from local context:

- System mechanics: repeatable workflows, safety rules, validation scripts, and lifecycle procedures.
- Local context: project profiles, durable decisions, known traps, and curated wiki pages produced by real work.

The repository should teach a new user what to do next at each stage without requiring them to understand every directory first.

For clean distribution and safe upgrades, treat the reusable starter and each populated local repository as different roles. The starter owns generic system mechanics and generic knowledge; an instance owns local projects, organization-specific skills, raw sessions, incidents, and curated project memory. See [Starter And Instance Sync Plan](starter-instance-sync.md) for the update model.

## First Run

1. Clone the clean starter repository for a new installation, or use this populated repository only when intentionally working in this instance.
2. Copy `.env.template` to `.env`.
3. Fill local path variables in `.env`.
4. Read `AGENTS.md`.
5. Read `AGENTS.local.md` if it exists in this checkout.
6. Read `README.local.md` if it exists in this checkout.
7. Read this guide.
8. Read `projects/README.md`.
9. Read `projects/index.local.md` if it exists in this checkout.
10. Read `references/index.local.md` if it exists in this checkout.
11. Add or update project profiles for the repositories you will work on.

Do not commit `.env`, raw logs, raw session notes, or developer-specific absolute home-directory paths.

Use `AGENTS.local.md` and `README.local.md` for committed instance-specific rules and setup notes that should not become starter-managed system content. Keep local secret values and developer paths in `.env`, not in local Markdown files.

## Add Projects

For each external project:

1. Add or update `projects/<project>.md`.
2. Use variables defined by `.env.template` or local instance instructions instead of local absolute paths.
3. Record repository URLs, default branch, setup commands, test commands, and important related projects.
4. Link durable background material in `references/` only when the material remains useful outside one task.
5. Link wiki context packs only when a reusable cross-session context exists.

Project profiles should answer: where is the project, how do I safely inspect it, how do I verify changes, and what should I not forget?

## Solve Problems

When starting work:

1. Read `AGENTS.md`.
2. Read the relevant project profile.
3. Use task-specific skills from `.codex/skills/`.
4. Use `wiki/index.md` when the task involves cross-session context, lifecycle validation, long agent runs, or repository memory.
5. Inspect source files before editing code.
6. Run the smallest meaningful verification before broader checks.

Use `tmp/` for ad hoc raw artifacts while exploring. Move only curated, sanitized outputs into durable repository locations.

## Close A Session

When the user asks to save, preserve, wrap up, or close a session:

1. Capture raw local notes under `wiki/sessions/`.
2. Treat raw notes as low-trust input.
3. Promote only durable knowledge into committed memory, and only when the user asked for memory updates or approval is clear.
4. Report raw capture and durable promotion separately, including `none` when no durable memory was created.

Expected report shape:

```text
Raw capture: wiki/sessions/<date>-<slug>.md
Durable memory: <path> or none
Verification: <commands>
Commit: yes/no
Push: yes/no
```

## Extract Knowledge

After one or more solved problems, decide what should become durable:

- Global rule: update `AGENTS.md`.
- Repeatable procedure: update or create a skill under `.codex/skills/`.
- Project-specific path, command, or relationship: update `projects/<project>.md`.
- Long-lived background material or decision support: update `references/`.
- Cross-session context, known traps, or wiki lifecycle material: update `wiki/`.
- Incident evidence: create curated incident Markdown under `incidents/<date>-<slug>/`.

Do not turn every session note into memory. Durable memory should reduce future work or prevent future mistakes.

## LLM Wiki Flow

Use the LLM wiki when a task benefits from curated cross-session context. The starter includes the generic lifecycle mechanics; each populated instance owns its raw notes, concepts, context packs, and decisions.

Typical flow:

```text
wiki/sessions/      raw local capture, ignored by git
wiki/drafts/        proposed promotion, reviewable
wiki/concepts/      approved stable concepts
wiki/context-packs/ approved task-routing context
wiki/decisions/     approved decision records
```

Run these checks before treating wiki content as ready:

```bash
uv run python scripts/wiki_lint.py
uv run python scripts/wiki_lint.py --profile autonomous
uv run python scripts/wiki_status.py
```

When checking lint behavior itself:

```bash
uv run python scripts/tests/test_wiki_lint.py
```

## Temporary Artifacts

Use these locations:

- `tmp/`: ad hoc local collection before a case exists.
- `incidents/<case>/artifacts/`: raw local incident artifacts for a specific case.
- `wiki/sessions/`: raw local session notes.

These raw-artifact locations are ignored by git. Curated records should be moved into tracked Markdown only after review and sanitization.

## Update From Starter

Existing instances should receive future starter improvements through an explicit sync workflow, not by rebasing onto starter history.

Starter-owned updates can include generic scripts, generic skills, onboarding documents, validation rules, and generic system knowledge under managed namespaces such as `references/system/` or `wiki/system/`. User-owned paths such as `projects/`, `wiki/sessions/`, `wiki/drafts/`, `wiki/concepts/`, `wiki/context-packs/`, `wiki/decisions/`, `wiki/fixtures/`, `wiki/validation-runs/`, and `incidents/` must remain reserved for the instance.

Before applying starter updates:

1. Make sure the instance worktree is clean.
2. Run the sync check or dry-run command.
3. Review safe updates, new files, skipped user paths, and conflicts.
4. Resolve conflicts explicitly instead of overwriting local memory.
5. Run validation commands.
6. Commit the starter update as one reviewable change.

The sync design is defined in [Starter And Instance Sync Plan](starter-instance-sync.md). Use `scripts/sync_system.py --check`, `--dry-run`, `--adopt`, and `--apply` for starter updates. The `--allow-local-adopt` and `--allow-local-apply` flags are only for local bootstrap or development validation; normal updates should use a release tag or a full pinned commit.

Starter maintainers should use [Starter Release Procedure](starter-release-procedure.md) before tagging a clean release.

## What To Do Next

After a clean checkout:

1. Configure `.env`.
2. Add the first project profile.
3. Solve one small task with the agent.
4. Close the session and confirm a raw note appears under `wiki/sessions/`.
5. Promote one durable learning only if it will help future work.
6. Run checks.
7. Commit only curated changes.

The system is working when the user can always answer three questions:

- Where should this information go?
- Is it raw local input or durable committed memory?
- What check proves it is safe enough for the next step?
