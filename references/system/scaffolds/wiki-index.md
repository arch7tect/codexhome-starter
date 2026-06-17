---
status: active
updated: 2026-06-17
confidence: decision
expires: 2027-06-17
sources:
  - AGENTS.md
  - references/getting-started-with-codexhome.md
  - references/starter-instance-sync.md
tags:
  - llm-wiki
  - starter
---

# LLM Wiki Index

This wiki stores repository memory that is useful across sessions. Treat it as curated support for normal repository context, not as a replacement for source files, project profiles, skills, or maintainer decisions.

## System Pages

- [Lifecycle](system/lifecycle.md) - capture, promote, verify, publish, review, and archive workflow.
- [Page Contract](system/page-contract.md) - required frontmatter, source discipline, ownership, and expiry rules.

## User-Owned Areas

- `wiki/sessions/`: raw local session notes, ignored by git.
- `wiki/drafts/`: proposed changes awaiting maintainer review.
- `wiki/concepts/`: stable concepts maintained by the local instance.
- `wiki/context-packs/`: compact task-routing context maintained by the local instance.
- `wiki/decisions/`: durable local decision records.
- `wiki/fixtures/`: local validation fixtures.
- `wiki/validation-runs/`: local validation output.

## Read Order

For normal CodexHome work, read `AGENTS.md` and the relevant project profile first. Use this wiki when the task involves repository memory, lifecycle validation, cross-session context, or long agent runs.
