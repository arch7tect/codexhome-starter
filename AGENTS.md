# Codex Home Instructions

Treat this repository as the local Codex home. It may contain persistent memory, dialogue context, skills, helper code, and related working notes.

Project conventions:

- All documents and code in this repository must be written in English.
- Code comments should be minimal and used only when they explain how or why something works, not what the code plainly does.
- Use Python for repository scripts.
- Manage Python dependencies and script execution with `uv`. If a script needs a missing library, install it with `uv`.
- Commit messages must be one-line messages.
- Commit messages must not mention AI.
- When asked to preserve session learnings, wrap up work, update memory, or create reusable procedures, use the session memory review workflow before committing.
- Before studying or changing code in a project repository, fetch remote refs and update the local branch to the latest upstream state when this can be done without overwriting local uncommitted work. If the worktree is dirty or local commits diverge, inspect and report the state before relying on local code as current.
- Do not store developer-specific absolute home-directory paths in memory, project profiles, skills, or references. Use neutral variables defined by `.env.template`, project profiles, or local instance instructions instead.
- Store local developer path values in gitignored `.env`; keep `.env.template` as the committed variable contract. Load `.env` before running commands that depend on those variables.
- If `AGENTS.local.md` exists, read it after this file for instance-specific rules, variable names, project families, or local overlays. If the current agent runtime does not auto-load it, inspect it manually before using local context.
- When a user asks to initialize or bootstrap this CodexHome instance, run `uv run python scripts/bootstrap_instance.py` from the repository root. Bootstrap creates `.env` from `.env.template` with placeholder values. Do not infer, discover, or write real local paths into `.env` unless the user explicitly provides those values in the same request; otherwise tell the user to edit `.env` after bootstrap.

Repository layout:

- `AGENTS.md` stores global agent behavior, repository conventions, and workflow rules.
- `AGENTS.local.md`, when present, stores instance-specific rules that should not be copied into a clean starter repository.
- `.codex/skills/` stores reusable procedures. Each real skill should live in its own directory with a `SKILL.md` entrypoint.
- `projects/` stores project profiles, links between related projects, local paths, commands, and project-specific context.
- `references/` stores longer background material, examples, and documents that skills or instructions may reference.
