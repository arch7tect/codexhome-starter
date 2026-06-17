# Starter And Instance Sync Plan

This document defines how CodexHome should separate reusable system mechanics from user-specific or organization-specific knowledge, and how an existing instance can safely receive future starter updates.

## Goal

CodexHome needs two distribution shapes:

- A clean starter repository that contains portable system mechanics, generic skills, generic documentation, validation scripts, and empty scaffolding.
- A populated instance repository that contains real project profiles, raw local sessions, curated decisions, organization-specific skills, incident records, and local operating context.

The starter must be safe to publish and clone without leaking this instance's project history or knowledge. Existing instances must still be able to receive future starter improvements without overwriting local memory.

## Repository Roles

Use a fresh-history starter/template repository for new users. Do not derive the starter as a long-lived branch or fork of a populated instance, because history can leak deleted project context, incidents, paths, and skills.

Keep populated repositories as instances. An instance may contain:

- local project profiles;
- organization-specific skills;
- raw session captures;
- curated wiki decisions, concepts, and context packs;
- incident reports and local artifacts;
- instance-specific operating rules.

Starter releases should be tagged with semantic versions such as `v0.1.0`, `v0.2.0`, and so on. Instances should pull starter improvements through an explicit sync workflow, not by rebasing onto the starter.

The release gate and tagging workflow are defined in [Starter Release Procedure](starter-release-procedure.md).

## Path Classes

The sync model is default-deny: any path not listed in the manifest is user-owned and must not be modified by starter sync.

Every important top-level path must have exactly one effective class before sync can apply changes. Conditional ownership rules such as "managed when generic" are not operational enough for the sync script. A file is either byte-generic and starter-owned, or it is local and must be split or reserved before first sync.

Baseline classification:

| Path | Class | Notes |
| --- | --- | --- |
| `AGENTS.md` | managed | Portable starter rules only. Existing local or organization-specific rules must move to `AGENTS.local.md` before sync. |
| `AGENTS.local.md` | scaffold_once | Created from an optional template when missing, then local-owned. |
| `CLAUDE.md` | managed | Portable Claude Code orientation only. |
| `README.md` | managed | Starter-level orientation only. Instance-specific content must move to a reserved path or local overlay before sync. |
| `README.local.md` | scaffold_once | Optional local instance overview, never overwritten after creation. |
| `.env.template` | managed | Portable variable contract. |
| `.env` | scaffold_once | Local and ignored after creation. |
| `.gitignore` | managed | Generic ignore rules only. Local untracked ignore needs should use `.git/info/exclude`. |
| `.codex/skills/README.md` | managed | Generic directory rules only. |
| `.codex/skills/<generic-skill>/` | managed | Only when explicitly listed in the manifest. |
| `.codex/skills/<local-skill>/` | reserved_user | Default for any skill directory not explicitly listed as managed. |
| `references/README.md` | managed | Generic directory rules only. |
| `references/index.local.md` | scaffold_once | Optional local reference index, never overwritten after creation. |
| `references/system/**` | managed | Generic system documents. |
| `references/<local-doc>.md` | reserved_user | Default for unlisted reference documents. |
| `projects/README.md` | managed | Generic directory rules only. |
| `projects/_template.md` | scaffold_once | Project profile template for new instances. |
| `projects/index.local.md` | scaffold_once | Optional local project index, never overwritten after creation. |
| `projects/*` | reserved_user | Except explicitly listed scaffold templates. |
| `incidents/README.md` | managed | Generic directory rules only. |
| `incidents/*` | reserved_user | Includes incident reports and artifacts. |
| `wiki/index.md` | scaffold_once | Generic wiki entrypoint created when missing, then local-owned. |
| `wiki/system/**` | managed | Generic wiki lifecycle and operating knowledge. |
| `wiki/sessions/` | reserved_user | Raw local capture, ignored by git. |
| `wiki/drafts/` | reserved_user | Proposed local promotion drafts. |
| `wiki/concepts/` | reserved_user | Instance-maintained concepts. |
| `wiki/context-packs/` | reserved_user | Instance-maintained context packs. |
| `wiki/decisions/` | reserved_user | Instance-maintained decisions. |
| `wiki/fixtures/` | reserved_user | Local validation fixtures and experiment data. |
| `wiki/validation-runs/` | reserved_user | Local validation output. |
| `scripts/wiki_common.py` | managed | Generic wiki lifecycle support. |
| `scripts/wiki_lint.py` | managed | Generic wiki lint command. |
| `scripts/wiki_status.py` | managed | Generic wiki health report command. |
| `scripts/wiki_promote.py` | managed | Generic promotion draft command. |
| `scripts/tests/test_wiki_lint.py` | managed | Generic wiki lint regression tests. |
| `scripts/system_lock.py` | managed | Generic system-lock hashing and decision support. |
| `scripts/tests/test_system_lock.py` | managed | Generic system-lock regression tests. |
| `scripts/sync_system.py` | managed | Generic starter sync check, dry-run, and apply command. |
| `scripts/bootstrap_instance.py` | managed | Thin first-run bootstrap wrapper around starter sync apply. |
| `scripts/tests/test_sync_system.py` | managed | Generic starter sync regression tests. |
| `scripts/tests/test_bootstrap_instance.py` | managed | First-run bootstrap regression tests. |
| `scripts/wiki_metrics.py` | reserved_user | Validation experiment tooling, not starter core. |
| `scripts/<generic-script>.py` | managed | Only generic repository maintenance scripts explicitly listed in the manifest. |
| `scripts/*` | reserved_user | Default for unlisted scripts, local experiments, and optional packs not included in the current starter release. |
| `system-manifest.toml` | managed | Frozen for the current sync run. Manifest updates require a second run to take effect. |
| `instance-manifest.toml` | scaffold_once | Optional local overlay; reservations here always win. |
| `system-lock.toml` | managed | Starter sync baseline hashes and provenance. |

### Managed

Managed paths are owned by the starter and can be updated by sync after conflict checks. They must contain no user-editable or organization-specific content.

Expected managed paths:

- explicitly listed `scripts/<generic-script>.py` entries for generic repository maintenance scripts, including the wiki lifecycle scripts shipped by the starter;
- `README.md` for starter-level orientation;
- `CLAUDE.md` for portable Claude Code orientation;
- explicitly listed starter reference documents such as onboarding and sync architecture;
- `references/system/**` for generic system documents;
- `wiki/system/**` for generic wiki lifecycle and operating knowledge;
- directory rule documents such as `.codex/skills/README.md`, `references/README.md`, `projects/README.md`, and `incidents/README.md`;
- explicitly listed generic skill directories under `.codex/skills/<skill-name>/`;
- `.env.template` as the portable environment variable contract;
- `AGENTS.md` after local rules have been split into `AGENTS.local.md`;
- `system-manifest.toml`, `system-lock.toml`, and the sync script itself.

Managed paths should be listed at file or skill-directory granularity. Do not classify whole mixed directories such as `.codex/skills/` or `scripts/` as managed, because instances can contain local skills and optional scripts.

### Scaffold Once

Scaffold-once paths are created during initial setup when missing, then become user-owned.

Expected scaffold-once paths:

- `.env` copied from `.env.template`;
- `AGENTS.local.md` for local or organization-specific instructions;
- `README.local.md` for local instance orientation when needed;
- `references/index.local.md` for local reference indexes when needed;
- `projects/_template.md` for the initial project profile template;
- `projects/index.local.md` for local project indexes when needed;
- `wiki/index.md` for local wiki navigation when needed;
- `instance-manifest.toml` for local sync policy overlays when needed;
- local placeholder files for ignored directories when needed;
- optional local config files that should never be overwritten after first creation.

The lockfile records that a scaffold-once file was already created. If a user deletes that file later, sync does not recreate it unless explicitly requested.

Existing instances can backfill scaffold-once creation state with `--adopt`; this records currently present scaffold-once files without changing their content.

`instance-manifest.toml` is local-owned even though the sync tool reads it on every run. Starter sync must never overwrite it after creation.

The first supported `instance-manifest.toml` overlay is reservation-only:

```toml
schema_version = 1

[[paths]]
path = "AGENTS.md"
class = "reserved_user"
note = "Local policy is intentionally customized in this instance."
```

Only `reserved_user` entries are accepted. These reservations are evaluated before `system-manifest.toml`, so they protect even paths that the starter manifest classifies as managed.

### Reserved User

Reserved-user paths are never modified by starter sync.

Expected reserved-user paths:

- `projects/*` except starter-owned templates explicitly listed as scaffold-once;
- `incidents/*`;
- `wiki/sessions/`;
- `wiki/drafts/`;
- `wiki/concepts/`;
- `wiki/context-packs/`;
- `wiki/decisions/`;
- `wiki/fixtures/`;
- `wiki/validation-runs/`;
- organization-specific or user-created `.codex/skills/<skill-name>/` directories;
- raw artifacts, logs, local notes, and generated working files.

This reservation leaves `wiki/system/**` and `references/system/**` as the starter-owned homes for generic knowledge. User-maintained wiki knowledge stays in the existing wiki areas.

## Mixed-Content Files

A managed file must not mix starter-owned system content with local content. Mixed files are the largest source of unsafe updates because a future sync cannot know which paragraphs belong to the starter and which belong to the instance.

Use explicit split points:

- `AGENTS.md` should contain portable starter rules only.
- `AGENTS.local.md` should contain local or organization-specific instructions.
- `README.md` should contain starter-level orientation only.
- `README.local.md` should contain local instance orientation when needed.
- `.env.template` should be managed; `.env` should be local and ignored.
- `.gitignore` should contain generic ignore rules only; developer-local ignore rules should go in `.git/info/exclude`.
- `system-manifest.toml` should be managed; an optional `instance-manifest.toml` can add instance-local reservations or policy without editing the starter manifest.

If an instance needs to customize a managed file, first move the customization into a local overlay or a reserved path.

Splitting customized managed files is a mandatory pre-sync migration. The sync tool should refuse to apply when a managed file was locally customized and has no approved overlay or conflict resolution.

## Manifest And Lockfile

Use a manifest-driven sync with a committed lockfile.

The locally committed `system-manifest.toml` is authoritative for the current sync run. An incoming starter manifest may update the local manifest as a managed file, but its new classifications must not affect the same run; the user must re-run sync after reviewing the manifest update. If `instance-manifest.toml` exists, its reservations always win over starter classifications.

`system-manifest.toml` should define:

- manifest schema version;
- starter release version;
- path entries with class: `managed`, `scaffold_once`, or `reserved_user`;
- content type for managed entries, such as `text` or `binary`;
- per-entry ownership notes;
- optional verification commands for updated components;
- prune policy, defaulting to no automatic deletion.

`system-lock.toml` should record, for each synced managed file:

- source starter version;
- normalized content hash such as `sha256`;
- path class at the time of sync;
- when the file was introduced or last updated;
- optional source path or release reference.

Hash normalization should be explicit and stable. Text files use UTF-8, LF line endings, and a single trailing newline. Binary files are hashed as raw bytes. The manifest should declare the content type for managed entries; if a bootstrap tool infers type, it must record the chosen type before hashing. The same normalization must be used when writing the lockfile and when checking local files.

The lockfile enables a real three-way decision:

- Local file equals the last synced hash and starter changed: fast-forward.
- Local file equals the last synced hash and starter did not change: no-op.
- Local file changed and starter did not change: keep local.
- Local file changed and starter changed: stop with a conflict.
- Starter adds a managed file that is absent locally: safe new file.
- Starter adds a managed file whose path already exists locally and is not in the lockfile: stop with a conflict.
- Local and starter both changed but converged to identical normalized content: no-op after updating lockfile provenance.
- Local deleted a managed file that starter still contains: stop and ask whether to restore, keep deleted, or reserve locally.
- Starter removed a managed file that local still has unchanged from the last synced hash: report as a prune candidate, but do not delete without explicit prune.
- A path class changes between the lockfile and the current manifest: stop for explicit review.
- A managed path content type changes between the lockfile and the current manifest: stop for explicit review.

Do not rely on `git status` alone for this decision. Git can show whether the worktree is clean, but it cannot identify the starter baseline for a managed file.

Prune must obey the same safety model as updates. It may only remove managed files that still match the last synced hash, and only when the user explicitly enables prune.

Manifest-provided verification commands are a trust boundary. Sync should run verification commands only from trusted starter sources, and command execution should be opt-in or clearly disclosed before apply.

Manifest schema bumps that require structural migrations are out of scope for the first sync implementation. A sync tool should block on unsupported schema versions until a reviewed migration exists.

First sync onto a populated instance is expected to produce conflicts for pre-existing managed paths that have no lockfile baseline. A bootstrap adopt mode may write lockfile baselines without changing file content only after the user reviews each adopted path as starter-owned and byte-generic. Bootstrap lockfile writes must be visible in the same reviewable worktree diff as any other sync output.

## User-Facing Update Workflow

The update path should be understandable for users who are not Git experts.

Recommended command shape:

```bash
uv run python scripts/sync_system.py --from <starter-repo-or-tag> --manifest system-manifest.toml --check
uv run python scripts/sync_system.py --from <starter-repo-or-tag> --manifest system-manifest.toml --dry-run
uv run python scripts/sync_system.py --from <starter-repo-or-tag> --manifest system-manifest.toml --adopt
uv run python scripts/sync_system.py --from <starter-repo-or-tag> --manifest system-manifest.toml --apply
```

The first implementation supports `--dry-run` and `--apply` from a local starter path, a semver release tag such as `v0.1.0`, or a full 40-character pinned commit. Adopt writes `system-lock.toml` baselines only for matching managed paths and requires a semver tag or full pinned commit by default. Local-path adopt and apply are reserved for explicit bootstrap or development runs with `--allow-local-adopt` and `--allow-local-apply`.

Instance bootstrap adopt should preserve scaffold-once creation state so a user's later deletion is respected. A clean starter release baseline is different: it must be generated with `--managed-only-lock` so the shipped lockfile contains managed baselines but no scaffold-once markers. Otherwise a fresh clone would treat files such as `.env` and `wiki/index.md` as already created and skip first-run scaffolding.

Required behavior:

1. Refuse to run on a dirty worktree, except for an explicit status/check mode.
2. Resolve starter source from a trusted release tag or pinned commit and copy it into a temporary directory.
3. Use the same transaction contract for dry-run and apply so dry-run cannot disagree with apply blockers.
4. Group output into safe updates, new managed files, adopt candidates, scaffold-once creations, conflicts, skipped user paths, prune candidates, reported managed changes, and skipped generated paths.
5. Apply only fast-forwards and safe new files that are absent locally.
6. For conflicts, write starter-side comparison files or a conflict report and stop.
7. Never delete removed upstream files automatically; require an explicit prune mode.
8. Run relevant read-only validation commands after apply, respecting the verification-command trust boundary, or deliberately include any validation-generated changes in the same reviewed sync commit.
9. Leave one reviewable worktree diff by default; optional commit mode may create one commit after validation passes.

Copy operations must reject symlinks, hard links, special files, absolute paths, and `..` path traversal from archive sources.

`--apply` uses a transaction contract before mutating the worktree:

1. Build the complete sync plan using the same planner as `--dry-run`.
2. Refuse to expose write operations when the plan has dirty worktree state, conflicts, adopt candidates, or reported managed changes other than `noop_update_lock`.
3. Re-check that the worktree is still clean immediately before the first write.
4. Write only safe updates, new managed files, and missing scaffold-once files.
5. Replace each file atomically on the same filesystem and refuse destination symlinks.
6. Update `system-lock.toml` last, after all file writes succeed. A `noop_update_lock` item is a lock-only apply update: when local and starter content already match, apply may refresh the stale baseline without copying the file.
7. Never prune during normal apply; pruning requires a separate explicit mode.

Conflict choices should be explicit:

- keep local;
- accept starter;
- copy local content upstream into the starter when it is generic;
- manually merge.

## Starter Promotion Gate

Before moving any content from an instance into the starter, verify that it is generic.

Promotion checklist:

- No organization-specific project names, tenant names, incident details, private repository URLs, or internal hostnames.
- No secrets, tokens, API keys, private logs, or raw artifacts.
- No developer-specific absolute home-directory paths.
- Written in English.
- Useful to more than one instance.
- Placed in a managed namespace such as `references/system/`, `wiki/system/`, an explicitly listed generic script, or an explicitly generic `.codex/skills/<skill-name>/`.
- Covered by the sync manifest and validation checks.

Instance-specific knowledge should remain in reserved-user paths.

## Failure Modes

The main risks are:

- Mixed-content managed files overwrite local policy.
- A new starter skill collides with an existing local skill.
- An unlisted path is accidentally treated as starter-owned.
- Starter content leaks organization-specific knowledge.
- The sync script deletes files that an instance still depends on.
- A lockfile mismatch causes false safety.
- Users apply a starter update together with unrelated local changes.
- Future starter releases require structural migrations instead of copy-only updates.

Mitigations:

- Default-deny path classification.
- Per-file or per-skill manifest entries.
- `system-lock.toml` hashes for managed files.
- Clean-tree precondition for apply.
- No automatic deletion.
- Conflict stop instead of overwrite.
- One reviewable commit per sync.
- Rare structural changes shipped as explicit migrations, not as normal sync behavior.

## Initial Implementation Plan

1. Add this architecture document and link it from onboarding.
2. Split any mixed system/local documentation before implementing sync.
3. Add `references/system/` and `wiki/system/` when the first generic system knowledge needs to be managed.
4. Draft `system-manifest.toml` for the current starter surface.
5. Draft [System Lock Format](system/system-lock-format.md) and tests for three-way decisions.
6. Implement `scripts/sync_system.py` as a copy-only sync with check, dry-run, and apply modes.
7. Validate with a temporary fixture instance before using it on a real populated instance.
8. Create the fresh-history starter repository only after the promotion gate passes.
