# Incident Cases

This directory is the only canonical home for durable incident and diagnostic
cases managed through CodexHome. Product repositories may keep minimal,
sanitized regression fixtures, but must not keep case archives, raw evidence, or
incident reports.

## Case identity and layout

Create cases with:

```bash
uv run python scripts/incident_case.py create \
  --system <system> \
  --slug <short-topic> \
  --title "<title>" \
  --owner <owner> \
  --environment <environment>
```

The canonical path is immutable after the case reaches `reported`:

```text
incidents/<YYYY-MM-DD-system-topic>/
  case.yaml
  report.md
  timeline.md
  analysis/
  queries/
  repro/
  evidence/
    sanitized/
    OBJECTS.yaml
  redactions.md
  knowledge.yaml
  local/
```

`case.yaml` stores the stable UUID, lifecycle state, affected systems, safe
aliases, privacy review, evidence state, retention, and provenance. Put
verbatim complaints, tenant/session/communication identifiers, raw logs,
transcripts, screenshots, WAV files, environment snapshots, database extracts,
ZIP files, and working notes under `local/`.

Legacy case aliases such as `product-a:cases/44` resolve through
`LEGACY-MAP.md`. Do not create redirect directories or per-case stubs in product
repositories.

## Storage tiers

| Tier | Location | Policy |
|---|---|---|
| Committed case record | This private Git repository | Reviewed `case.yaml`, report, timeline, analysis, queries, repro scripts, redaction notes, knowledge dispositions, and small sanitized evidence. Maximum 1 MiB, 25 files, and 256 KiB per file. |
| Local evidence | `incidents/<case>/local/` | Gitignored raw, sensitive, bulky, duplicate, or working evidence. It is not a sufficient sole durable copy. |
| Private evidence store | Approved encrypted object storage | Required before deleting the final source copy of evidence that must survive local retention. Encrypt locally with independent primary and escrow `age` recipients before upload. Commit only stable object identifiers, hashes, sizes, restore receipts, and retention metadata; never commit credentials, private identities, remote paths, or presigned URLs. |
| Product fixture | Product repository test fixture directory | Minimal, sanitized, owned by a named automated test, and linked by case UUID. It is not an incident archive and must not live under `cases/`. |

Committed files must be UTF-8 with LF line endings. Binary evidence, generated
HTML, screenshots, audio, packet captures, raw logs, and archives are never
committed as case records.

## Encrypted evidence offload

Use the `incident-evidence-offload` skill for this workflow. It is the
operational procedure for `scripts/evidence_offload.py`, key custody, remote
restore drills, rotation, and guarded source cleanup.

A corporate Google Shared Drive is suitable as the second durable evidence
store when it is used only for ciphertext. Do not upload raw evidence, rely on
Drive permissions as the encryption boundary, or place evidence in a personal
My Drive folder. Use a dedicated Shared Drive folder with corporate retention
and access controls. The local `age` primary identity and independently held
escrow identity are the decryption boundary.

Configure the Drive as an `rclone` remote locally and set
`INCIDENT_EVIDENCE_RCLONE_DESTINATION` in `.env`. Never commit the rclone
configuration, OAuth material, private age identities, or the destination
path. Create the primary identity on the operating workstation and the escrow
identity under independent corporate custody.

### Public age recipient registry

`PUBLIC-AGE-RECIPIENTS.yaml` is the canonical instance-owned registry for
public encryption recipients. A fresh starter creates it once from
`PUBLIC-AGE-RECIPIENTS.example.yaml`; an empty registry means evidence offload
has not been configured yet. Incident validation accepts that state only while
no committed receipt references a recipient. Bundle, upload, restore, and
finalize operations require configured active primary and escrow recipients.
The registry's name, `kind`, notice, and
`public_age_recipient` field deliberately state that the values are public.
The file must never contain an age private identity, vault secret, password,
OAuth material, recovery code, or remote path.

Register a public recipient only after its private identity has reached the
declared custody location and a restore or derivation check confirms the
mapping. Use stable registry IDs in commands and receipts. New bundles may use
only `active` entries. Rotation adds a new versioned ID and bundle; retain the
old public entry as `retired` so historical receipts remain verifiable.
`compromised` entries are also retained for audit but must not encrypt new
bundles.

The registry contains key and custody metadata only. Do not duplicate case
UUIDs or other per-case usage in it. Committed `case.yaml` restore receipts are
the source of truth. List and validate the safe registry, then derive the
recipient-to-case mapping from those receipts with:

```bash
uv run python scripts/evidence_offload.py recipients
uv run python scripts/evidence_offload.py recipient-usage
```

For a hash-first migrated case:

```bash
uv run python scripts/evidence_offload.py keygen --label <primary-label>
uv run python scripts/evidence_offload.py bundle \
  --case <case-id> \
  --recipient-id <primary-public-recipient-id> \
  --recipient-id <escrow-public-recipient-id>
uv run python scripts/evidence_offload.py upload \
  --case <case-id> \
  --destination "$INCIDENT_EVIDENCE_RCLONE_DESTINATION"
uv run python scripts/evidence_offload.py drill \
  --case <case-id> \
  --custody primary \
  --identity-keyring <primary-label> \
  --from-remote
uv run python scripts/evidence_offload.py drill \
  --case <case-id> \
  --custody escrow \
  --identity-file <escrow-identity-file> \
  --from-remote
uv run python scripts/evidence_offload.py finalize --case <case-id>
```

`bundle` verifies every source file against `local/import-manifest.jsonl`,
recomputes each variant tree and the aggregate case root, creates a
deterministic tar and Zstandard archive, and encrypts it for at least two
active registry recipients covering the primary and escrow roles. Remote names
contain only the case UUID and ciphertext hash; the
deterministic plaintext archive hash is never exposed in the object name.
`upload` rejects duplicate names, records a stable provider object ID, and
verifies a fresh ciphertext download. Each `drill`
uses a fresh private directory and independently verifies ciphertext,
decryption, archive hash, safe member types and paths, every object hash, file
and byte counts, variant trees, and the aggregate root.

`finalize` changes evidence state to `offloaded` only after both the primary and
escrow identities have restored the downloaded remote object with distinct
keys. It rechecks the unique provider object ID and downloads and hashes the
ciphertext again before committing the receipt. Google Drive does not provide
object lock, so this content verification and the retained source copy remain
necessary. The committed receipt does not authorize deletion. Before deleting
the last legacy source,
also perform the escrow drill on an independent machine, verify product replay
resolution and cross-links, observe the applicable cooling period, and obtain
explicit user approval.

For a resumable multi-case migration, run a dry plan first:

```bash
uv run python scripts/evidence_offload.py batch --dry-run
```

Then load `.env` and run:

```bash
uv run python scripts/evidence_offload.py batch --continue-on-error
```

The batch command selects `local-only` hash-first cases, uses the single active
primary and escrow public registry IDs, and resumes from each case's ignored
local state. It never uploads plaintext and does not delete source evidence.
Its ignored JSONL journal records stage progress; only finalized safe receipts
belong in Git. Use repeated `--case` options or `--limit` for a pilot.

Migrated symlink evidence is archived as regular content-addressed bytes plus a
validated relative `symlink_target` field in the encrypted manifest. Restore
materializes a regular file and never creates a symlink, preventing traversal
while preserving the original link metadata for analysis.

## Lifecycle

Case state and evidence state are independent:

- Case: `open` → `investigating` → `explained` → `reported` →
  `knowledge-extracted` → `closed`.
- Side exits: `inconclusive`, `duplicate`, and `imported`.
- Evidence: `none`, `local-only`, `offloaded`, or `purged`.

A `reported` case needs a privacy-reviewed `report.md`. A
`knowledge-extracted` or `closed` case needs `knowledge.yaml` with at least one
explicit disposition, including `none` with a reason when the case yields no
durable general knowledge.

Run:

```bash
uv run python scripts/incident_case.py validate
uv run python scripts/incident_case.py index
```

## What a case may teach

Evaluate every completed case for these destinations:

- project profile: stable project-specific commands, contracts, or ownership;
- reusable skill: a repeatable diagnostic or recovery procedure;
- research bundle: bounded evidence needed to compare or validate a claim;
- wiki concept, decision, or context pack: reviewed durable cross-session
  knowledge;
- monitoring change: a missing signal or operational guardrail;
- product fixture: a minimal sanitized regression owned by a test;
- `none`: no durable generalization, with the reason recorded.

Promote a generalized rule only after two independent cases support it or one
case demonstrates the mechanism directly. Record version, environment, tenant,
carrier, provider, or other scope limits. Preserve negative results and
counterexamples. Use `observed`, `probable`, and `speculative` confidence;
speculative conclusions stay case-scoped or become research questions.

Review speculative knowledge within 90 days, probable knowledge within 180
days, and observed knowledge within 365 days.

## Migration and deletion guard

Legacy migration is hash-first and restartable:

1. inventory every active checkout, backup, and worktree variant;
2. copy every source byte into the ignored local object store;
3. verify hashes and materialize per-case local variants;
4. commit only safe aggregate manifests and alias mappings;
5. repair cross-repository links and extract required regression fixtures;
6. create a second durable copy and perform a restore drill;
7. delete source cases only after explicit approval.

Directory-name equality is not deduplication. Merge only byte-identical objects;
preserve distinct backup or worktree variants until a maintainer adjudicates
them. Removing files from a repository tip does not remove them from Git
history; history remediation requires a separate coordinated decision.
