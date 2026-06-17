from __future__ import annotations

from pathlib import Path
import tarfile
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_system import (  # noqa: E402
    Manifest,
    ManifestEntry,
    SyncPlan,
    SyncPlanItem,
    adopt_lockfile,
    apply_sync_plan,
    atomic_copy_file,
    build_apply_transaction,
    build_sync_plan,
    classify_path,
    dry_run_blockers,
    hash_optional_file,
    is_trusted_starter_ref,
    load_lockfile,
    load_manifest,
    lock_source_label,
    resolve_starter_source,
    safe_extract_archive,
    scaffold_creation_hash,
)
from system_lock import normalized_sha256  # noqa: E402


def test_manifest_loads() -> None:
    manifest = load_manifest(ROOT / "system-manifest.toml")
    if manifest.schema_version != 1:
        raise AssertionError("unexpected schema version")
    if manifest.matching != "specific_before_glob":
        raise AssertionError("unexpected matching strategy")
    if len(manifest.entries) < 50:
        raise AssertionError("manifest loaded too few entries")


def test_manifest_requires_starter_version() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "manifest_validation"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    write_text(base / "system-manifest.toml", 'schema_version = 1\ndefault_class = "reserved_user"\n')

    try:
        load_manifest(base / "system-manifest.toml", base)
    except ValueError as exc:
        if "starter_version" not in str(exc):
            raise AssertionError(f"unexpected manifest validation error: {exc}") from exc
    else:
        raise AssertionError("manifest without starter_version should be rejected")


def test_lockfile_requires_hex_sha256() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "lock_validation"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    write_text(base / "system-lock.toml", """[[paths]]
path = "managed.txt"
class = "managed"
content = "text"
sha256 = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
""")

    try:
        load_lockfile(base / "system-lock.toml")
    except ValueError as exc:
        if "invalid sha256" not in str(exc):
            raise AssertionError(f"unexpected lockfile validation error: {exc}") from exc
    else:
        raise AssertionError("lockfile should reject non-hex sha256 values")


def test_specific_before_glob() -> None:
    manifest = Manifest(
        schema_version=1,
        starter_version="test",
        default_class="reserved_user",
        matching="specific_before_glob",
        verification_commands=[],
        entries=[
            ManifestEntry("references/*", "reserved_user"),
            ManifestEntry("references/README.md", "managed", "text"),
            ManifestEntry("wiki/*", "reserved_user"),
            ManifestEntry("wiki/system/**", "managed", "text"),
            ManifestEntry("wiki/index.md", "scaffold_once", "text"),
        ],
    )

    cases = {
        "references/README.md": "managed",
        "references/local.md": "reserved_user",
        "wiki/system/lifecycle.md": "managed",
        "wiki/index.md": "scaffold_once",
        "wiki/concepts/example.md": "reserved_user",
    }
    for rel_path, expected in cases.items():
        entry = classify_path(manifest, rel_path)
        if entry is None or entry.path_class != expected:
            actual = None if entry is None else entry.path_class
            raise AssertionError(f"{rel_path}: expected {expected}, got {actual}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def item_paths(items: list[object]) -> set[str]:
    return {getattr(item, "path") for item in items}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout)
    return result.stdout.strip()


def test_dry_run_groups_sync_actions() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "sync_system"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    old_hash = normalized_sha256(b"old\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "updated.txt"
class = "managed"
content = "text"

[[paths]]
path = "new.txt"
class = "managed"
content = "text"

[[paths]]
path = "conflict.txt"
class = "managed"
content = "text"

[[paths]]
path = "adopt.txt"
class = "managed"
content = "text"

[[paths]]
path = "removed.txt"
class = "managed"
content = "text"

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"

[[paths]]
path = "existing_seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"

[[paths]]
path = "local.txt"
class = "reserved_user"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "updated.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"

[[paths]]
path = "removed.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"
""")

    write_text(local / "updated.txt", "old\n")
    write_text(starter / "updated.txt", "new\n")
    write_text(starter / "new.txt", "new\n")
    write_text(local / "conflict.txt", "local\n")
    write_text(starter / "conflict.txt", "starter\n")
    write_text(local / "adopt.txt", "same\n")
    write_text(starter / "adopt.txt", "same\n")
    write_text(local / "removed.txt", "old\n")
    write_text(local / "existing_seed.md", "custom\n")
    write_text(local / "local.txt", "local\n")
    write_text(local / "scaffold.md", "seed\n")
    write_text(starter / "scaffold.md", "seed\n")

    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)

    if item_paths(plan.safe_updates) != {"updated.txt"}:
        raise AssertionError(f"unexpected safe updates: {plan.safe_updates}")
    if item_paths(plan.new_managed_files) != {"new.txt"}:
        raise AssertionError(f"unexpected new managed files: {plan.new_managed_files}")
    if item_paths(plan.conflicts) != {"conflict.txt"}:
        raise AssertionError(f"unexpected conflicts: {plan.conflicts}")
    if item_paths(plan.adopt_candidates) != {"adopt.txt"}:
        raise AssertionError(f"unexpected adopt candidates: {plan.adopt_candidates}")
    if item_paths(plan.prune_candidates) != {"removed.txt"}:
        raise AssertionError(f"unexpected prune candidates: {plan.prune_candidates}")
    if item_paths(plan.scaffold_once_creations) != {"seed.md"}:
        raise AssertionError(f"unexpected scaffold creations: {plan.scaffold_once_creations}")
    if not {"existing_seed.md", "local.txt"}.issubset(item_paths(plan.skipped_user_paths)):
        raise AssertionError(f"unexpected skipped user paths: {plan.skipped_user_paths}")


def test_adopt_writes_lockfile_for_matching_managed_paths() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "sync_system_adopt"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "same.txt"
class = "managed"
content = "text"

[[paths]]
path = "local.md"
class = "scaffold_once"
content = "text"
source = "seed.md"

[[paths]]
path = "notes.txt"
class = "reserved_user"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "same.txt", "same\n")
    write_text(starter / "same.txt", "same\n")
    write_text(local / "local.md", "custom\n")
    write_text(local / "seed.md", "seed\n")
    write_text(starter / "seed.md", "seed\n")
    write_text(local / "notes.txt", "local\n")

    plan, adopted = adopt_lockfile(local, starter, "system-manifest.toml")

    if plan.conflicts:
        raise AssertionError(f"unexpected adopt conflicts: {plan.conflicts}")
    if item_paths(adopted) != {"same.txt", "local.md"}:
        raise AssertionError(f"unexpected adopted entries: {adopted}")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if set(paths) != {"same.txt", "local.md"}:
        raise AssertionError(f"unexpected lockfile paths: {paths}")
    if paths["same.txt"]["class"] != "managed" or paths["same.txt"]["content"] != "text":
        raise AssertionError(f"unexpected lockfile entry: {paths['same.txt']}")
    if paths["local.md"]["class"] != "scaffold_once":
        raise AssertionError(f"unexpected scaffold lockfile entry: {paths['local.md']}")


def test_adopt_refreshes_stale_matching_lockfile_entry() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "sync_system_adopt_refresh"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "same.txt"
class = "managed"
content = "text"
"""
    stale_hash = normalized_sha256(b"old\n", "text")
    fresh_hash = normalized_sha256(b"fresh\n", "text")
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "same.txt"
class = "managed"
content = "text"
sha256 = "{stale_hash}"
""")
    write_text(local / "same.txt", "fresh\n")
    write_text(starter / "same.txt", "fresh\n")

    plan, adopted = adopt_lockfile(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")

    if plan.conflicts:
        raise AssertionError(f"unexpected adopt refresh conflicts: {plan.conflicts}")
    if item_paths(adopted) != {"same.txt"}:
        raise AssertionError(f"unexpected refreshed entries: {adopted}")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if len(lock["paths"]) != 1 or paths["same.txt"]["sha256"] != fresh_hash:
        raise AssertionError(f"stale lockfile entry was not refreshed: {lock}")


def test_adopt_backfills_existing_scaffold_once_lock_entry() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "sync_system_adopt_scaffold"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "seed.md", "customized local seed\n")
    write_text(local / "scaffold.md", "starter seed\n")
    write_text(starter / "scaffold.md", "starter seed\n")

    plan, adopted = adopt_lockfile(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")

    if plan.conflicts:
        raise AssertionError(f"unexpected scaffold adopt conflicts: {plan.conflicts}")
    if item_paths(adopted) != {"seed.md"}:
        raise AssertionError(f"unexpected scaffold adopted entries: {adopted}")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if paths["seed.md"]["class"] != "scaffold_once":
        raise AssertionError(f"unexpected scaffold lockfile entry: {paths['seed.md']}")
    if paths["seed.md"]["sha256"] != scaffold_creation_hash("seed.md"):
        raise AssertionError(f"scaffold backfill should not hash local content: {paths['seed.md']}")


def test_managed_only_adopt_omits_existing_scaffold_once_entries() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "sync_system_adopt_managed_only"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    managed_hash = normalized_sha256(b"same\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "same.txt"
class = "managed"
content = "text"

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "same.txt"
class = "managed"
content = "text"
sha256 = "{managed_hash}"

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
sha256 = "{scaffold_creation_hash("seed.md")}"
""")
    write_text(local / "same.txt", "same\n")
    write_text(starter / "same.txt", "same\n")
    write_text(local / "seed.md", "customized local seed\n")
    write_text(local / "scaffold.md", "starter seed\n")
    write_text(starter / "scaffold.md", "starter seed\n")

    plan, adopted = adopt_lockfile(
        local,
        starter,
        "system-manifest.toml",
        "v1.2.3@abcdef123456",
        include_scaffold_once=False,
    )

    if plan.conflicts:
        raise AssertionError(f"unexpected managed-only adopt conflicts: {plan.conflicts}")
    if item_paths(adopted) != set():
        raise AssertionError(f"managed-only adopt should not adopt scaffold entries: {adopted}")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if set(paths) != {"same.txt"}:
        raise AssertionError(f"managed-only release lock should omit scaffold entries: {paths}")


def test_lock_source_label_is_portable() -> None:
    root = Path("/tmp/example")
    if lock_source_label(root, root) != ".":
        raise AssertionError("same-root source should be stored as .")
    if lock_source_label(root, root / "starter") != "starter":
        raise AssertionError("nested source should be stored relative to local root")


def test_starter_ref_trust_rules() -> None:
    trusted = {"v1.2.3", "v1.2.3-rc.1", "0123456789abcdef0123456789abcdef01234567"}
    untrusted = {"main", "release", "v1", "0123456", "feature/test"}
    for source in trusted:
        if not is_trusted_starter_ref(source):
            raise AssertionError(f"expected trusted source: {source}")
    for source in untrusted:
        if is_trusted_starter_ref(source):
            raise AssertionError(f"expected untrusted source: {source}")


def test_resolve_starter_source_from_tag_archive() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "starter_ref"
    if base.exists():
        shutil.rmtree(base)
    repo = base / "repo"
    repo.mkdir(parents=True)
    git(repo, "init")
    write_text(repo / "system-manifest.toml", 'schema_version = 1\nstarter_version = "test"\ndefault_class = "reserved_user"\n')
    write_text(repo / "managed.txt", "starter\n")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "init")
    git(repo, "tag", "v1.2.3")

    with resolve_starter_source("v1.2.3", repo) as source:
        if not source.label.startswith("v1.2.3@"):
            raise AssertionError(f"unexpected source label: {source.label}")
        if source.is_local_path:
            raise AssertionError("tag source should not be marked as local path")
        if not (source.path / "managed.txt").exists():
            raise AssertionError("archived starter source is missing managed.txt")
        if (source.path / ".git").exists():
            raise AssertionError("archived starter source should not contain .git")


def test_resolve_starter_source_marks_local_path() -> None:
    with resolve_starter_source(".", ROOT) as source:
        if not source.is_local_path:
            raise AssertionError("local source should be marked as local path")


def test_archive_extraction_rejects_special_files() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "special_archive"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    archive_path = base / "special.tar"
    destination = base / "out"
    destination.mkdir()

    with tarfile.open(archive_path, mode="w") as archive:
        special = tarfile.TarInfo("device")
        special.type = tarfile.CHRTYPE
        archive.addfile(special)

    try:
        safe_extract_archive(archive_path, destination)
    except ValueError as exc:
        if "special files" not in str(exc):
            raise AssertionError(f"unexpected special-file error: {exc}") from exc
    else:
        raise AssertionError("special archive member should be rejected")


def test_text_hash_matches_local_crlf_and_tag_archive() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "hash_equivalence"
    if base.exists():
        shutil.rmtree(base)
    repo = base / "repo"
    repo.mkdir(parents=True)
    git(repo, "init")
    write_text(repo / ".gitattributes", "*.txt text\n")
    (repo / "managed.txt").write_bytes(b"line one\r\nline two\r\n")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "init")
    git(repo, "tag", "v1.2.3")

    local_hash = hash_optional_file(repo, "managed.txt", "text")
    with resolve_starter_source("v1.2.3", repo) as source:
        archived_hash = hash_optional_file(source.path, "managed.txt", "text")

    if local_hash != archived_hash:
        raise AssertionError("text hash should match local CRLF content and normalized tag archive content")


def test_apply_transaction_allows_only_safe_write_operations() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "apply_transaction"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    old_hash = normalized_sha256(b"old\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "updated.txt"
class = "managed"
content = "text"

[[paths]]
path = "new.txt"
class = "managed"
content = "text"

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "updated.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"
""")
    write_text(local / "updated.txt", "old\n")
    write_text(starter / "updated.txt", "new\n")
    write_text(starter / "new.txt", "new\n")
    write_text(local / "scaffold.md", "seed\n")
    write_text(starter / "scaffold.md", "seed\n")

    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)
    transaction = build_apply_transaction(plan)

    if transaction.blockers:
        raise AssertionError(f"unexpected apply blockers: {transaction.blockers}")
    if item_paths(transaction.operations) != {"updated.txt", "new.txt", "seed.md"}:
        raise AssertionError(f"unexpected apply operations: {transaction.operations}")
    if not transaction.clean_recheck_required or not transaction.lockfile_update_last:
        raise AssertionError("apply transaction must require clean recheck and lockfile-last update")


def test_apply_transaction_blocks_ambiguous_or_dirty_plans() -> None:
    dirty_plan = SyncPlan(
        safe_updates=[SyncPlanItem("updated.txt", "managed", "fast_forward", "apply", "safe update")],
        new_managed_files=[SyncPlanItem("new.txt", "managed", "safe_new", "apply", "safe new")],
        adopt_candidates=[SyncPlanItem("adopt.txt", "managed", "adopt_baseline", "report", "needs baseline")],
        scaffold_once_creations=[],
        conflicts=[SyncPlanItem("conflict.txt", "managed", "conflict", "stop", "both changed")],
        skipped_user_paths=[],
        prune_candidates=[],
        reported_managed_changes=[SyncPlanItem("local.txt", "managed", "keep_local", "report", "local changed")],
        skipped_generated_paths=[],
        noop_count=0,
        lock_entry_count=1,
        dirty=[" M unrelated.txt"],
    )
    transaction = build_apply_transaction(dirty_plan)

    expected = {
        "worktree must be clean before apply",
        "conflicts require explicit review before apply",
        "adopt candidates require lockfile baseline before apply",
        "reported managed changes require explicit review before apply",
    }
    if set(transaction.blockers) != expected:
        raise AssertionError(f"unexpected apply blockers: {transaction.blockers}")
    if transaction.operations:
        raise AssertionError(f"blocked transaction must not expose operations: {transaction.operations}")


def test_dry_run_blockers_match_apply_transaction() -> None:
    plan = SyncPlan(
        safe_updates=[SyncPlanItem("updated.txt", "managed", "fast_forward", "apply", "safe update")],
        new_managed_files=[],
        adopt_candidates=[SyncPlanItem("adopt.txt", "managed", "adopt_baseline", "report", "needs baseline")],
        scaffold_once_creations=[],
        conflicts=[],
        skipped_user_paths=[],
        prune_candidates=[],
        reported_managed_changes=[],
        skipped_generated_paths=[],
        noop_count=0,
        lock_entry_count=0,
        dirty=[],
    )

    if dry_run_blockers(plan) != build_apply_transaction(plan).blockers:
        raise AssertionError("dry-run blockers must use the same transaction contract as apply")
    if "adopt candidates require lockfile baseline before apply" not in dry_run_blockers(plan):
        raise AssertionError(f"dry-run should block on adopt candidates: {dry_run_blockers(plan)}")


def test_apply_transaction_allows_lock_only_update() -> None:
    plan = SyncPlan(
        safe_updates=[],
        new_managed_files=[],
        adopt_candidates=[],
        scaffold_once_creations=[],
        conflicts=[],
        skipped_user_paths=[],
        prune_candidates=[],
        reported_managed_changes=[
            SyncPlanItem("same.txt", "managed", "noop_update_lock", "report", "local and starter converged")
        ],
        skipped_generated_paths=[],
        noop_count=0,
        lock_entry_count=1,
        dirty=[],
    )
    transaction = build_apply_transaction(plan)

    if transaction.blockers:
        raise AssertionError(f"lock-only update should not block apply: {transaction.blockers}")
    if transaction.operations:
        raise AssertionError(f"lock-only update should not expose file writes: {transaction.operations}")
    if item_paths(transaction.lock_updates) != {"same.txt"}:
        raise AssertionError(f"unexpected lock updates: {transaction.lock_updates}")


def test_apply_sync_plan_writes_safe_operations_and_updates_lockfile() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "apply_sync"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    old_hash = normalized_sha256(b"old\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "updated.txt"
class = "managed"
content = "text"

[[paths]]
path = "new.txt"
class = "managed"
content = "text"

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "updated.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"
""")
    write_text(local / "updated.txt", "old\n")
    write_text(starter / "updated.txt", "new\n")
    write_text(starter / "new.txt", "brand new\n")
    write_text(local / "scaffold.md", "seed\n")
    write_text(starter / "scaffold.md", "seed\n")

    result = apply_sync_plan(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")

    if set(result.written_paths) != {"updated.txt", "new.txt", "seed.md"}:
        raise AssertionError(f"unexpected written paths: {result.written_paths}")
    if not result.lockfile_updated:
        raise AssertionError("managed writes should update lockfile")
    if set(result.lock_updated_paths) != {"updated.txt", "new.txt", "seed.md"}:
        raise AssertionError(f"unexpected lock-updated paths: {result.lock_updated_paths}")
    if (local / "updated.txt").read_text(encoding="utf-8") != "new\n":
        raise AssertionError("updated managed file was not replaced")
    if (local / "new.txt").read_text(encoding="utf-8") != "brand new\n":
        raise AssertionError("new managed file was not created")
    if (local / "seed.md").read_text(encoding="utf-8") != "seed\n":
        raise AssertionError("scaffold file was not created")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if set(paths) != {"updated.txt", "new.txt", "seed.md"}:
        raise AssertionError(f"unexpected lockfile paths after apply: {paths}")
    if paths["seed.md"]["class"] != "scaffold_once":
        raise AssertionError(f"unexpected scaffold lockfile entry: {paths['seed.md']}")
    if paths["seed.md"]["sha256"] != scaffold_creation_hash("seed.md"):
        raise AssertionError(f"scaffold apply should record marker hash: {paths['seed.md']}")
    if lock["source"] != "v1.2.3@abcdef123456":
        raise AssertionError(f"unexpected lockfile source: {lock['source']}")


def test_generated_lockfile_path_is_skipped_by_plan() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "generated_lockfile"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "system-lock.toml"
class = "managed"
content = "text"
generated = true
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", "schema_version = 1\nsource = \"local\"\n")
    write_text(starter / "system-lock.toml", "schema_version = 1\nsource = \"starter\"\n")

    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)

    if item_paths(plan.skipped_generated_paths) != {"system-lock.toml"}:
        raise AssertionError(f"generated lockfile should be skipped: {plan.skipped_generated_paths}")
    if plan.safe_updates or plan.conflicts or plan.reported_managed_changes:
        raise AssertionError(f"generated lockfile should not reach managed decisions: {plan}")


def test_apply_sync_plan_updates_lock_for_converged_content_without_file_write() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "apply_lock_only"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    stale_hash = normalized_sha256(b"old\n", "text")
    fresh_hash = normalized_sha256(b"fresh\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "same.txt"
class = "managed"
content = "text"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "same.txt"
class = "managed"
content = "text"
sha256 = "{stale_hash}"
""")
    write_text(local / "same.txt", "fresh\n")
    write_text(starter / "same.txt", "fresh\n")

    result = apply_sync_plan(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")

    if result.written_paths:
        raise AssertionError(f"lock-only apply should not write files: {result.written_paths}")
    if result.lock_updated_paths != ["same.txt"]:
        raise AssertionError(f"unexpected lock-only update paths: {result.lock_updated_paths}")
    if not result.lockfile_updated:
        raise AssertionError("lock-only apply should update lockfile")

    lock = tomllib.loads((local / "system-lock.toml").read_text(encoding="utf-8"))
    paths = {item["path"]: item for item in lock["paths"]}
    if paths["same.txt"]["sha256"] != fresh_hash:
        raise AssertionError(f"stale lockfile entry was not refreshed: {lock}")


def test_scaffold_once_lock_prevents_recreation_after_delete() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "scaffold_once_delete"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    seed_hash = normalized_sha256(b"seed\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
sha256 = "{seed_hash}"
""")
    write_text(local / "scaffold.md", "seed\n")
    write_text(starter / "scaffold.md", "seed\n")

    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)

    if plan.scaffold_once_creations:
        raise AssertionError(f"deleted scaffold-once path should not be recreated: {plan.scaffold_once_creations}")
    skipped = {item.path: item.action for item in plan.skipped_user_paths}
    if skipped.get("seed.md") != "skip_deleted_scaffold_once":
        raise AssertionError(f"unexpected skipped scaffold-once paths: {plan.skipped_user_paths}")


def test_apply_created_scaffold_once_is_not_recreated_after_delete() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "scaffold_apply_delete"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "seed.md"
class = "scaffold_once"
content = "text"
source = "scaffold.md"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "scaffold.md", "seed\n")
    write_text(starter / "scaffold.md", "seed\n")

    result = apply_sync_plan(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")
    if result.written_paths != ["seed.md"]:
        raise AssertionError(f"unexpected scaffold apply writes: {result.written_paths}")

    (local / "seed.md").unlink()
    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)

    if plan.scaffold_once_creations:
        raise AssertionError(f"apply-created scaffold should not be recreated: {plan.scaffold_once_creations}")
    skipped = {item.path: item.action for item in plan.skipped_user_paths}
    if skipped.get("seed.md") != "skip_deleted_scaffold_once":
        raise AssertionError(f"unexpected skipped scaffold after delete: {plan.skipped_user_paths}")


def test_apply_sync_plan_refuses_destination_symlink() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "apply_symlink"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "new.txt"
class = "managed"
content = "text"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(starter / "new.txt", "new\n")
    write_text(local / "target.txt", "local\n")
    (local / "new.txt").symlink_to("target.txt")

    try:
        apply_sync_plan(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")
    except ValueError as exc:
        if "symlinks are not supported" not in str(exc):
            raise AssertionError(f"unexpected symlink refusal: {exc}") from exc
    else:
        raise AssertionError("apply should refuse destination symlink")


def test_apply_sync_plan_refuses_symlink_to_matching_baseline() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "apply_symlink_baseline"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    old_hash = normalized_sha256(b"old\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "managed.txt"
class = "managed"
content = "text"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "managed.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"
""")
    write_text(local / "target.txt", "old\n")
    write_text(starter / "managed.txt", "new\n")
    (local / "managed.txt").symlink_to("target.txt")

    try:
        apply_sync_plan(local, starter, "system-manifest.toml", "v1.2.3@abcdef123456")
    except ValueError as exc:
        if "symlinks are not supported" not in str(exc):
            raise AssertionError(f"unexpected symlink baseline refusal: {exc}") from exc
    else:
        raise AssertionError("apply should refuse symlink even when target matches baseline")


def test_atomic_copy_file_refuses_destination_symlink() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "atomic_symlink"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    source = base / "source.txt"
    target = base / "target.txt"
    destination = base / "destination.txt"
    write_text(source, "source\n")
    write_text(target, "target\n")
    destination.symlink_to("target.txt")

    try:
        atomic_copy_file(source, destination)
    except ValueError as exc:
        if "destination symlink" not in str(exc):
            raise AssertionError(f"unexpected atomic symlink refusal: {exc}") from exc
    else:
        raise AssertionError("atomic copy should refuse destination symlink")


def test_instance_manifest_reservation_overrides_managed_path() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "instance_manifest"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    starter = base / "starter"
    local.mkdir(parents=True)
    starter.mkdir(parents=True)

    old_hash = normalized_sha256(b"old\n", "text")
    manifest = """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[verification]
commands = []

[[paths]]
path = "protected.txt"
class = "managed"
content = "text"
"""
    instance_manifest = """schema_version = 1

[[paths]]
path = "protected.txt"
class = "reserved_user"
"""
    write_text(local / "system-manifest.toml", manifest)
    write_text(starter / "system-manifest.toml", manifest)
    write_text(local / "instance-manifest.toml", instance_manifest)
    write_text(local / "system-lock.toml", f"""[[paths]]
path = "protected.txt"
class = "managed"
content = "text"
sha256 = "{old_hash}"
""")
    write_text(local / "protected.txt", "old\n")
    write_text(starter / "protected.txt", "new\n")

    plan = build_sync_plan(local, starter, "system-manifest.toml", require_clean=False)

    if plan.safe_updates:
        raise AssertionError(f"reserved instance path must not become safe update: {plan.safe_updates}")
    if "protected.txt" not in item_paths(plan.skipped_user_paths):
        raise AssertionError(f"unexpected skipped user paths: {plan.skipped_user_paths}")


def test_instance_manifest_rejects_non_reserved_entries() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "instance_manifest_invalid"
    if base.exists():
        shutil.rmtree(base)

    local = base / "local"
    local.mkdir(parents=True)
    write_text(local / "system-manifest.toml", 'schema_version = 1\nstarter_version = "test"\ndefault_class = "reserved_user"\n')
    write_text(local / "instance-manifest.toml", """schema_version = 1

[[paths]]
path = "managed.txt"
class = "managed"
content = "text"
""")

    try:
        load_manifest(local / "system-manifest.toml", local)
    except ValueError as exc:
        if "must be reserved_user" not in str(exc):
            raise AssertionError(f"unexpected instance manifest error: {exc}") from exc
    else:
        raise AssertionError("instance manifest must reject non-reserved entries")


def main() -> int:
    test_manifest_loads()
    test_manifest_requires_starter_version()
    test_lockfile_requires_hex_sha256()
    test_specific_before_glob()
    test_dry_run_groups_sync_actions()
    test_adopt_writes_lockfile_for_matching_managed_paths()
    test_adopt_refreshes_stale_matching_lockfile_entry()
    test_adopt_backfills_existing_scaffold_once_lock_entry()
    test_managed_only_adopt_omits_existing_scaffold_once_entries()
    test_lock_source_label_is_portable()
    test_starter_ref_trust_rules()
    test_resolve_starter_source_from_tag_archive()
    test_resolve_starter_source_marks_local_path()
    test_archive_extraction_rejects_special_files()
    test_text_hash_matches_local_crlf_and_tag_archive()
    test_apply_transaction_allows_only_safe_write_operations()
    test_apply_transaction_blocks_ambiguous_or_dirty_plans()
    test_dry_run_blockers_match_apply_transaction()
    test_apply_transaction_allows_lock_only_update()
    test_apply_sync_plan_writes_safe_operations_and_updates_lockfile()
    test_generated_lockfile_path_is_skipped_by_plan()
    test_apply_sync_plan_updates_lock_for_converged_content_without_file_write()
    test_scaffold_once_lock_prevents_recreation_after_delete()
    test_apply_created_scaffold_once_is_not_recreated_after_delete()
    test_apply_sync_plan_refuses_destination_symlink()
    test_apply_sync_plan_refuses_symlink_to_matching_baseline()
    test_atomic_copy_file_refuses_destination_symlink()
    test_instance_manifest_reservation_overrides_managed_path()
    test_instance_manifest_rejects_non_reserved_entries()
    print("sync_system tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
