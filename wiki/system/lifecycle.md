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
  - lifecycle
---

# LLM Wiki Lifecycle

Use the wiki when a task produces context that should survive beyond one session. The lifecycle keeps raw notes separate from committed knowledge.

## Procedures

- `capture`: save raw local notes under `wiki/sessions/` without treating them as verified.
- `promote`: create a draft under `wiki/drafts/` from selected raw notes or user-approved findings.
- `verify`: check sources, confidence, expiry, links, and placement before publication.
- `publish`: apply only maintainer-approved durable changes.
- `review-stale`: inspect expired pages and pages nearing expiry.
- `archive`: retire stale knowledge only after approval and link repair.
- `lint`: run deterministic wiki checks.
- `report`: summarize drafts, stale pages, unresolved approvals, and verification status.

## Rules

- Raw notes are low-trust input and stay out of git by default.
- Durable wiki pages need explicit sources and a review expiry.
- Use project profiles, skills, and references as source-of-truth links instead of duplicating them.
- Scheduled jobs may report stale or broken pages, but must not publish raw notes automatically.
- See [Page Contract](page-contract.md) before publishing wiki content.
