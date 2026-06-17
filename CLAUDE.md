# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is a Codex home: a meta-repository holding persistent agent memory, reusable skills, project profiles, and reference material. It contains no application code of its own. The actual project code lives in separate repositories whose local paths, commands, and conventions are recorded in `projects/*.md` — read the relevant project profile before working on any external project.

Follow `AGENTS.md` — it is the authoritative source of global behavior rules, repository conventions, and the directory layout. If `AGENTS.local.md` exists, read it after `AGENTS.md` for instance-specific rules that should not be copied into a clean starter repository. Directory-specific rules live in `projects/README.md`, `.codex/skills/README.md`, `references/README.md`, and `incidents/README.md`.

Reusable procedures live in `.codex/skills/<skill-name>/SKILL.md`. These are not auto-loaded: before starting a repeatable task (incident investigation, memory updates, commit preparation, code review, diagnostics, etc.), list `.codex/skills/` and read the matching `SKILL.md` if one exists.
