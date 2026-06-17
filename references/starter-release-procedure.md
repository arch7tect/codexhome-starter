# Starter Release Procedure

This procedure gates a clean CodexHome starter release. It is separate from normal instance updates.

## Release Rule

Do not tag a populated instance tree as a starter release. A starter release must be built from a clean-history tree that contains only managed starter files and no instance-owned project profiles, local skills, incidents, wiki pilot history, raw notes, or local overlays.

The release tree may be a separate starter repository or a fresh-history export. A long-lived branch or normal tag on a populated instance repository is not enough, because Git history can still expose removed local context.

Push starter releases only to the dedicated clean starter remote. Never push release tags to a populated instance remote.

## Required Gate

Run these checks in the candidate release tree:

```bash
uv run python scripts/sync_system.py --check
uv run python scripts/wiki_lint.py
uv run python scripts/wiki_lint.py --profile autonomous
uv run python scripts/tests/test_wiki_lint.py
uv run python scripts/tests/test_system_lock.py
uv run python scripts/tests/test_sync_system.py
uv run python scripts/tests/test_release_hygiene.py
uv run python scripts/release_hygiene.py \
  --deny-term '<local-organization-name>' \
  --deny-term '<local-project-name>' \
  --deny-regex '<local-host-or-absolute-path-regex>'
```

The release hygiene check must pass with no tracked non-managed paths and no scaffold-once entries in `system-lock.toml`.

Before trusting a zero-match deny scan in the candidate release tree, validate the deny terms against the populated instance that the starter was derived from:

```bash
uv run python scripts/release_hygiene.py \
  --validate-deny-terms \
  --deny-term '<local-organization-name>' \
  --deny-term '<local-project-name>' \
  --deny-regex '<local-host-or-absolute-path-regex>'
```

This validation command should run in the populated instance and pass only when every deny term or regex matches at least one tracked file there. Then run the normal release hygiene command in the clean candidate and require zero matches.

## Lock Baseline

Before tagging a clean starter release, refresh the release tree lockfile as managed-only:

```bash
uv run python scripts/sync_system.py --adopt --from . --allow-local-adopt --managed-only-lock
```

Review `system-lock.toml` and confirm:

- every entry has `class = "managed"`;
- no entry has `class = "scaffold_once"`;
- no local absolute paths or organization-specific names appear.

The initial clean release baseline may use `source = "."` because the release tag does not exist yet. After an instance applies from the release tag, its local lockfile records tag provenance such as `v0.1.0@<commit>`.

## Tag Flow

1. Start from a clean release tree in the dedicated starter repository or fresh-history export, not the populated instance.
2. Run the lock baseline command.
3. Run the required gate.
4. Commit the release tree.
5. Tag the release in the clean starter repository or fresh-history export, for example `v0.1.0`.
6. Run an archive-source smoke test from the tag:

```bash
uv run python scripts/sync_system.py --from v0.1.0 --dry-run
```

7. Push the tag only to the dedicated clean starter remote after the smoke test and final review pass. Do not push the tag to the populated instance remote.

## Instance Upgrade Smoke

Before announcing the release, test a populated throwaway instance:

1. Add committed user-owned files under `projects/`, `references/`, `incidents/`, and `wiki/concepts/`.
2. Add ignored raw files under `tmp/` and `wiki/sessions/`.
3. Run `--dry-run` from the release tag.
4. Confirm the dry-run verdict has no apply blockers for the intended update.
5. Run `--apply` from the release tag.
6. Confirm the diff contains only expected managed updates and `system-lock.toml`.
7. Confirm user-owned files and ignored raw files are untouched.
