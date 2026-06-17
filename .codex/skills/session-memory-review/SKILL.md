---
name: session-memory-review
description: Review an interactive work session and update CodexHome memory, project profiles, references, or reusable skills when the user asks to preserve learnings, wrap up, update memory, create procedures, or capture durable project context.
---

# Session Memory Review

## Workflow

1. Read `AGENTS.md` and inspect `git status --short`.
2. Review the current session outcome and identify durable information only:
   - Project paths, repositories, ownership, relationships, and status.
   - Commands for setup, run, test, lint, build, deploy, and diagnostics.
   - Repository conventions, safety rules, architecture decisions, and recurring pitfalls.
   - Repeated workflows that should become skills.
   - Long-lived background context that should become references.
3. Ignore transient details:
   - One-off command output.
   - Temporary debugging hypotheses.
   - Secrets, tokens, passwords, private customer data, or copied credentials.
   - Facts likely to become stale unless they are tied to a stable workflow.
4. Choose the destination:
   - `AGENTS.md` for global rules that should affect every future turn.
   - `projects/*.md` for project-specific paths, commands, relationships, and notes.
   - `references/*.md` for longer durable context, decisions, investigations, or examples.
   - `.codex/skills/<skill-name>/SKILL.md` for repeatable procedures.
5. Prefer operational memory over passive storage:
   - Put actionable rules in the skill or project profile that will be loaded before the same work recurs.
   - Use `references/*.md` only for background, evidence, examples, or retrospective context that does not need to alter future workflow.
   - If a session mistake exposed a weakness in this memory workflow, update `session-memory-review` itself so the review procedure improves.
   - Do not create generic lesson, mistake, retrospective, or incident-investigation warehouse files. If one exists, break it apart into concrete skills/profiles/global rules and delete the warehouse file.
6. When creating or changing a skill, follow `.codex/skills/skill-creator/SKILL.md`:
   - Use lowercase hyphen-case names.
   - Include `agents/openai.yaml`.
   - Keep `SKILL.md` concise and move long details to references.
   - Validate with `uv run python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .codex/skills/<skill-name>`.
7. Keep memory updates in English, concise, and non-duplicative.
8. Use `apply_patch` for manual edits.
9. Verify the changed files with the smallest meaningful check:
   - Read the changed Markdown files.
   - Run skill validation for changed skills.
   - Inspect `git diff --stat` and `git diff` for intended files.
10. Report what changed, why each destination was used, validation results, and whether a commit is still needed.

## Commit Guidance

Commit memory updates separately from unrelated project implementation changes unless the user explicitly asks for one combined commit. Use a one-line commit message that does not mention AI.
