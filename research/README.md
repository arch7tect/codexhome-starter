# Research Evidence

Use this directory for durable, bounded investigation evidence. The wiki routes
future work and summarizes conclusions; a research bundle preserves the records
needed to verify those conclusions.

## Bundle contract

Name bundles `YYYY-MM-DD-project-topic`, using the investigation start date and
lowercase kebab-case. Do not append a materially different rerun to an existing
bundle; create a new bundle and link it with `supersedes` in its README.

Each bundle uses:

```text
research/<bundle-id>/
  README.md
  MANIFEST.yaml
  CHECKSUMS.sha256
  canonical/
  derived/
  judging/
  probes/
  scripts/
  validation/
  local/
```

- `canonical/`: safe source records for the committed bundle.
- `derived/`: small outputs reproducible from canonical records.
- `judging/`: blinded mappings, numeric scores, and batch indexes.
- `probes/`: bounded diagnostic results.
- `scripts/`: reproducibility and bundle-generation scripts.
- `validation/`: deterministic gate output or integrity summaries.
- `local/`: sensitive, heavy, duplicate, or regenerable evidence. It is
  gitignored but must be inventoried with hashes in `MANIFEST.yaml`.

`MANIFEST.yaml` is the provenance spine. List every bundle file except the
manifest and checksum file, including local-only evidence. Record its role,
disposition, SHA-256 digest, byte size, privacy/redaction state, and row count
when meaningful. Generate `CHECKSUMS.sha256` from committed manifest entries.

## Encoding and line endings

Store committed textual evidence and bundle metadata as UTF-8 with LF line
endings. Normalize line endings before calculating byte sizes or SHA-256
digests, and calculate hashes from the normalized bytes that Git will commit.
Do not publish checksums calculated from CRLF content that Git will later
normalize. `.gitattributes` enforces LF for tracked `research/` content, and the
evidence gate rejects committed files containing carriage returns.

Local-only evidence remains byte-for-byte source evidence. Do not normalize it
unless the investigation explicitly creates and inventories a derived,
normalized copy.

## Privacy and retention

Git history is permanent. Treat speech transcripts, free-form customer text,
session exports, and judge rationales derived from them as potentially
sensitive.

- Never commit audio, raw environment or integration dumps, credentials,
  generated HTML, or unreviewed patient-derived text.
- Store those artifacts under `local/` and preserve their hashes in the
  manifest.
- Commit transcript text only after explicit maintainer review. Mark the file
  `redaction: maintainer-reviewed` and record `reviewed_by` and `reviewed_at`.
- Prefer canonical JSON or JSONL over duplicate CSV. Commit only small derived
  tables used by the report or wiki.
- Use non-identifying clip IDs. Do not introduce patient or session identifiers
  into filenames.

If committed research evidence grows beyond 10 MB across the repository, or a
binary artifact becomes necessary, stop and choose a dedicated private evidence
store rather than expanding Git by default.

Gitignored does not mean disposable. Every manifest must define a retention
owner and expiry. Preserve `local/` until that expiry; when moving or replacing
the checkout, copy the local tier to an approved private location and verify its
hashes before deleting the original.

## Gate

Run before committing any bundle:

```bash
uv run python scripts/evidence_gate.py research/<bundle-id>
```

The gate verifies the manifest/tree match, file types and sizes, privacy
patterns, transcript-review policy, row counts, hashes, checksums, and that
`local/` content remains ignored and untracked.
