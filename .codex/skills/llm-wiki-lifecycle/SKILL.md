---
name: llm-wiki-lifecycle
description: Manage the CodexHome LLM-wiki lifecycle when the user asks to capture, promote, verify, publish, review stale wiki pages, archive wiki knowledge, lint wiki health, or report wiki maintenance status.
---

# LLM Wiki Lifecycle

Use this skill for the CodexHome LLM-wiki lifecycle. Keep durable repository memory human-owned and agent-assisted.

## Workflow

1. Read `AGENTS.md`, `wiki/index.md`, and `wiki/system/lifecycle.md`.
2. Inspect `git status --short` and do not touch unrelated worktree changes.
3. Identify the requested lifecycle action:
   - `capture`: save low-trust notes without treating them as verified knowledge.
   - `promote`: create a draft from selected notes under `wiki/drafts/`.
   - `verify`: check sources, confidence, owner, expiry, and placement.
   - `publish`: apply only maintainer-approved changes.
   - `review-stale`: inspect expired and soon-expiring pages.
   - `archive`: archive only after maintainer approval and repair links.
   - `lint`: run deterministic wiki checks when scripts exist.
   - `report`: summarize drafts, rejected notes, stale pages, and unresolved owner decisions.
4. When the user asks to save, preserve, capture, or wrap up the current session, always run `capture` first:
   - create or update a raw local note under gitignored `wiki/sessions/`;
   - mark it as low-trust local input;
   - then promote durable knowledge only if the user asked for memory updates or approval is clear.
5. Keep raw session notes out of git by default.
6. Prefer links to `AGENTS.md`, project profiles, skills, and references instead of duplicating content.
7. Do not publish verified wiki knowledge from raw notes without explicit maintainer approval.
8. Run the smallest relevant verification:
   - read changed wiki pages;
   - run available wiki lint/status scripts;
   - validate this skill when it changes.
9. Report raw capture and durable promotion separately:
   - raw capture path under `wiki/sessions/`, if created;
   - promoted or committed durable memory path, if created;
   - approval gate used, remaining risks, and whether a commit is needed.

## Placement Rules

- Use `wiki/context-packs/` for compact task routing context with contracts.
- Use `wiki/concepts/` for stable cross-session concepts.
- Use `wiki/decisions/` for durable local decisions.
- Use `wiki/drafts/` for proposed changes awaiting review.
- Use gitignored `wiki/sessions/` or external storage for raw notes.
- Use `wiki/system/` for generic lifecycle mechanics and page contracts.
