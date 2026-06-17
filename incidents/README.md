# Incidents

This directory stores curated incident records. Each incident must have one sendable `report.md`
that can be read without raw artifacts or chat context.

## Layout

```text
incidents/<date>-<slug>/
  report.md
  timeline.md
  recovery.md
  followups.md
  artifacts/
```

Commit curated Markdown and small sanitized examples only. Keep raw logs, JSON, TSV, screenshots, and
temporary dumps in `artifacts/` or case-local working directories; raw artifacts are ignored by
default.

Use top-level `tmp/` for ad hoc artifact collection before a case directory exists. Clean or move
only sanitized evidence into `incidents/<date>-<slug>/` when creating a durable incident record.

Do not place incident-specific working files under `references/`. Use `references/` only for reusable
background material that remains useful outside a single incident.
