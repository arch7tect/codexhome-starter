---
name: skill-creator
description: Create or update project-local CodexHome skills under `.codex/skills/`. Use when the user asks to create, refine, document, validate, or organize reusable Codex procedures for this repository, especially workflows that should become `SKILL.md` files with optional scripts, references, or assets.
---

# Skill Creator

## Workflow

1. Read `AGENTS.md` before editing skills.
2. Clarify concrete trigger examples unless the requested workflow is already specific.
3. Choose a short lowercase hyphen-case skill name. Use the same name for the folder.
4. Create or update `.codex/skills/<skill-name>/SKILL.md`.
5. Add only resources that directly support the skill:
   - `scripts/` for deterministic reusable commands.
   - `references/` for skill-specific detailed context.
   - `assets/` for templates or files used in outputs.
6. Use the repository-level `references/` directory for shared or long-lived background material.
7. Validate the skill and report the changed files.

## CodexHome Rules

- Write all skill files in English.
- Keep comments and explanatory prose minimal.
- Keep `SKILL.md` concise; move long examples or detailed background into references.
- Use Python for skill scripts.
- Manage Python dependencies and script execution with `uv`; install missing libraries with `uv`.
- Do not add README, changelog, installation guide, or other auxiliary docs inside a skill.
- Do not mention AI in commit messages.

## SKILL.md Requirements

Use only this frontmatter:

```yaml
---
name: skill-name
description: What the skill does and exactly when Codex should use it.
---
```

Write the body as imperative workflow guidance. Put trigger conditions in `description`, not in a body section, because the body loads only after the skill is selected.

When the skill supports multiple technologies, providers, or modes, keep selection guidance in `SKILL.md` and put variant-specific details in directly linked reference files.

## Metadata

If creating a new skill, include `agents/openai.yaml` with:

```yaml
interface:
  display_name: "Human-facing skill name"
  short_description: "Short UI description"
  default_prompt: "Use $skill-name to ..."
```

Keep `default_prompt` short and include the literal `$skill-name`.

## Commands

When the system `skill-creator` scripts are available, initialize new skills with:

```bash
uv run python "$HOME/.codex/skills/.system/skill-creator/scripts/init_skill.py" <skill-name> --path .codex/skills
```

Validate finished skills with:

```bash
uv run python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .codex/skills/<skill-name>
```

If the scripts are unavailable, manually verify the folder structure, YAML frontmatter, naming rules, and `agents/openai.yaml`.

## References

Read `references/agent-resources.md` when external examples, standards, or public skill libraries are useful.
