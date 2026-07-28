---
status: active
updated: 2026-07-29
confidence: decision
expires: 2027-07-29
sources:
  - references/getting-started-with-codexhome.md
  - scripts/wiki_common.py
tags:
  - llm-wiki
  - page-contract
---

# Wiki Page Contract

Every committed wiki page must be short, sourced, and reviewable. Follow the
[LLM Wiki Lifecycle](lifecycle.md) when capturing, promoting, verifying,
publishing, or retiring knowledge.

## Frontmatter

Required fields:

- `status`: lifecycle state such as `active`, `draft`, `stale`, or `archived`.
- `updated`: last meaningful review date in `YYYY-MM-DD` format.
- `confidence`: `observed`, `verified`, or `decision`.
- `expires`: next review date in `YYYY-MM-DD` format.
- `sources`: existing files or external links that justify the page.
- `tags`: grep-friendly routing labels.

## Placement

- Put starter-owned lifecycle mechanics under `wiki/system/`.
- Put low-trust raw notes under `wiki/sessions/`.
- Put proposed changes under `wiki/drafts/`.
- Put local concepts, context packs, and decisions under the corresponding user-owned wiki directories.
- Cite `incidents/<case-id>/report.md` for incident-derived knowledge and keep
  raw case evidence out of the wiki.
- Cite `research/<bundle-id>/README.md` for investigation evidence. Never embed run-level records, transcripts, or generated reports in wiki pages.
- Keep validation fixtures and experiment outputs out of the starter core.

## Review

Run wiki lint before relying on committed wiki content:

```bash
uv run python scripts/wiki_lint.py
uv run python scripts/wiki_lint.py --profile autonomous
```
