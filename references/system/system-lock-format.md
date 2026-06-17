# System Lock Format

`system-lock.toml` records the starter baseline for managed paths and scaffold-once creation state after an explicit bootstrap, adopt, or apply run. Do not hand-author baseline entries during normal documentation work.

## Purpose

The lockfile lets sync decide whether a managed path can fast-forward, must stop for conflict review, or should be reported as a prune candidate. It also records whether a scaffold-once path has already been created, so later user deletion is respected. It is separate from `system-manifest.toml`: the manifest states desired ownership, while the lock records the last accepted starter content hash for this instance.

## Entry Shape

Each synced managed or scaffold-once file entry should record:

- path;
- source starter version;
- path class at sync time;
- content type, such as `text` or `binary`;
- normalized `sha256`;
- introduced or updated timestamp;
- optional source path or release reference.

Text hashing uses UTF-8, LF line endings, and one trailing newline. Binary hashing uses raw bytes. The same normalization must be used when writing the lock and when checking local files.

An empty text file normalizes to a single trailing newline before hashing. Managed files that cannot be decoded as UTF-8 must be classified as `binary`.

The lockfile is generated state and must be excluded from its own three-way content evaluation. Sync may update `system-lock.toml` after applying or adopting managed files, but it must not use the previous lockfile entry for `system-lock.toml` to decide whether the lockfile can be rewritten.

## Decision Summary

The sync decision matrix is implemented in `scripts/system_lock.py` and covered by `scripts/tests/test_system_lock.py`. Each decision includes an action and a disposition: `apply`, `noop`, `report`, or `stop`.

- unchanged local plus changed starter: fast-forward;
- changed local plus unchanged starter: keep local;
- changed local plus changed starter: conflict unless both converged to identical content;
- missing local plus existing starter: stop for restore/keep/delete review;
- removed starter plus unchanged local: prune candidate, never automatic deletion;
- class or content-type changes: stop for explicit review.

Bootstrap/adopt may write initial lock entries only after the user has reviewed each adopted managed path as byte-generic starter content.

When a managed file's local content and starter content have already converged but the recorded baseline is stale, normal apply may perform a lock-only `noop_update_lock` refresh. This rewrites `system-lock.toml` last and does not copy file content.

For scaffold-once paths, adopt may backfill creation-state entries for files that already exist locally. These entries are not starter-owned update baselines; they prevent automatic recreation after a user deletes a scaffold-once file. Backfill uses a non-content creation marker hash instead of hashing local scaffold content, because scaffold-once files may contain local values such as `.env`.

Release baselines should be adopted from a semver tag or full pinned commit so the `source` field records release provenance such as `v0.1.0@<commit>`. `source = "."` is acceptable only for an initial clean release baseline before the release tag exists, or for an explicit local bootstrap or development baseline. After an instance applies from a release tag, its lockfile should record tag provenance.

A committed clean-starter release baseline must be managed-only: it should not contain scaffold-once entries. Instance lockfiles may record scaffold-once creation state, but shipping those markers in a starter would suppress first-run scaffolding for new users.
