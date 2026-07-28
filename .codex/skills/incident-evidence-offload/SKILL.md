---
name: incident-evidence-offload
description: Encrypt, upload, verify, restore, rotate, or retire durable incident evidence in CodexHome. Use when raw case evidence must survive local retention, move to an approved object store such as a corporate Google Shared Drive, pass primary and escrow restore drills, recover for replay, or satisfy source-cleanup gates.
---

# Incident Evidence Offload

Use `scripts/evidence_offload.py` from the CodexHome root. Follow
`incidents/README.md` as the storage contract. Treat the remote store as
untrusted transport and upload only locally encrypted ciphertext.

## Preflight

1. Load `.env` without printing it and resolve the canonical case.
2. Run `uv run python scripts/incident_case.py validate <case>`.
3. Confirm the case has hash-first local evidence and
   `local/import-manifest.jsonl`. Never synthesize missing raw evidence.
4. Run `uv run python scripts/evidence_offload.py recipients`. Confirm the
   selected public IDs are active, cover primary and escrow roles, and match
   the expected custody locations. An empty result means offload is not
   configured: generate or import the two identities, place the escrow private
   identity in approved independent custody, and add only their public
   recipients to the instance registry before continuing.
5. Inspect `uv run python scripts/evidence_offload.py status --case <case>`.
   `remote: null` is not an offload, and local drills do not prove remote
   recoverability.
6. Resolve the exact approved destination by stable folder or provider ID.
   Verify write capability before creating folders. Prefer a dedicated
   corporate Shared Drive location; do not silently fall back to My Drive.

## Key custody

- Encrypt for at least two distinct `age` X25519 recipients:
  - primary: the operating owner;
  - escrow: an independently retained private identity in the corporate
    secrets vault or another approved custodian.
- Store committed public recipients only in
  `incidents/PUBLIC-AGE-RECIPIENTS.yaml`. Use versioned public IDs in commands
  and receipts. Never print, commit, chat, log, or upload an
  `AGE-SECRET-KEY-...` value.
- Keep per-case usage out of the registry. Treat committed restore receipts as
  the source of truth and derive the inverse mapping with
  `uv run python scripts/evidence_offload.py recipient-usage`.
- Add a registry entry only after the private identity reaches the declared
  custody location and its derived public value has been verified. The
  registry must contain no vault item secret, password, OAuth material,
  recovery code, or remote path.
- A second key in the same local Keychain is only a pilot until its private
  identity is saved and retrieved from independent custody.
- Verify a vault copy by retrieving it through the vault, deriving its public
  recipient locally, comparing it with the bundle recipient, and running a
  remote restore. Use a `0600` temporary file only when the CLI requires one;
  delete it and clear the clipboard immediately.
- Keep the escrow copy until a second-machine restore passes. Do not remove the
  local fallback merely because the vault write succeeded.

## Bundle and upload

Create or import identities without exposing private values:

```bash
uv run python scripts/evidence_offload.py keygen --label <primary-label>
uv run python scripts/evidence_offload.py keygen --label <escrow-label>
```

Build by selecting the two active public registry IDs:

```bash
uv run python scripts/evidence_offload.py bundle \
  --case <case> \
  --recipient-id <primary-public-recipient-id> \
  --recipient-id <escrow-public-recipient-id>
```

The bundle command must verify every input hash, each variant tree, the
aggregate case root, and a non-empty inventory. Keep the encrypted bundle and
local state under the ignored `incidents/.local/offload/` tree.

Configure `rclone` locally. Use `--no-output` for OAuth configuration commands
that could otherwise print credential JSON. If a token is ever printed, revoke
it immediately, delete the affected remote, and authorize again without
output. Never commit rclone configuration or OAuth material.

Upload to the exact approved root:

```bash
uv run python scripts/evidence_offload.py upload \
  --case <case> \
  --destination <rclone-remote:path>
```

Require a unique remote name, stable provider object ID, fresh-download
ciphertext verification, and `roundtrip_ciphertext_verified: true`. A `403`
permission failure, duplicate name, missing object ID, or hash mismatch leaves
the case `local-only`.

## Restore drills and finalization

Restore the downloaded remote object with each distinct identity:

```bash
uv run python scripts/evidence_offload.py drill \
  --case <case> \
  --custody primary \
  --identity-keyring <primary-label> \
  --from-remote

uv run python scripts/evidence_offload.py drill \
  --case <case> \
  --custody escrow \
  --identity-file <vault-retrieved-identity> \
  --from-remote
```

Each drill must verify ciphertext, decryption, archive hash, safe member types
and paths, every object hash, file and byte counts, variant trees, and the
aggregate root. Primary and escrow receipts must name distinct public
recipients.

Finalize only after both remote drills pass:

```bash
uv run python scripts/evidence_offload.py finalize --case <case>
uv run python scripts/incident_case.py validate <case>
```

Finalization rechecks the unique provider object and ciphertext before writing
the privacy-safe `evidence.offload` receipt. It must not mutate the public
recipient registry. Commit and push only that reviewed case record. Keep remote
paths, local state, ciphertext, private identities, and credentials out of Git.

## Batch migration

For multiple hash-first cases, inspect the safe plan and then run the resumable
batch:

```bash
uv run python scripts/evidence_offload.py batch --dry-run
uv run python scripts/evidence_offload.py batch --continue-on-error
```

Load `.env` first. It supplies the approved destination and primary and escrow
Keychain labels. Use repeated `--case` options or `--limit` for a pilot. The
batch must process one case at a time, resume from ignored per-case state,
perform both remote drills, and finalize only complete cases. Review failures
from the ignored batch journal; never commit the journal.

Preserve migrated symlink metadata in the encrypted manifest, but restore its
content as a regular file. Never create archive-controlled symlinks.

## Recovery and rotation

- Use a remote drill as the default integrity-preserving recovery path.
- Restore into a fresh private directory or content-addressed replay cache.
  Verify the full case root before exposing any artifact to replay code.
- Treat missing or corrupt evidence as an infrastructure failure, never as an
  expected product replay result.
- Key rotation requires a new multi-recipient bundle, a new ciphertext object,
  both remote drills, and an updated receipt before changing the old public
  registry entry to `retired`. Keep retired and compromised public entries so
  historical receipts remain resolvable. Never overwrite the verified remote
  object in place.

## Source cleanup guard

`offloaded` does not authorize deletion. Keep
`source_deletion_authorized: false` until:

1. escrow restoration passes on an independent machine;
2. product replay resolution and every cross-link pass;
3. the retention or cooling period is satisfied;
4. the user explicitly approves the exact source deletion.

Delete legacy sources in a separate guarded change. Do not rewrite product Git
history unless the user authorizes a separate history-remediation project.
