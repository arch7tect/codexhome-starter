from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from release_hygiene import release_hygiene, validate_deny_terms  # noqa: E402
from sync_system import lockfile_text, LockEntry  # noqa: E402


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(repo: Path, *args: str) -> None:
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


def test_release_hygiene_rejects_tracked_non_managed_paths() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "release_hygiene_non_managed"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    git(base, "init")

    write_text(base / "system-manifest.toml", """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[[paths]]
path = "managed.txt"
class = "managed"
content = "text"

[[paths]]
path = "local.txt"
class = "reserved_user"
""")
    write_text(base / "system-lock.toml", lockfile_text([LockEntry("managed.txt", "managed", "text", "0" * 64)], "test", "."))
    write_text(base / "managed.txt", "managed\n")
    write_text(base / "local.txt", "local\n")
    git(base, "add", ".")

    violations = release_hygiene(base, [], [])

    if "tracked non-managed path: local.txt [reserved_user]" not in violations:
        raise AssertionError(f"expected non-managed violation: {violations}")


def test_release_hygiene_rejects_scaffold_lock_entries_and_deny_terms() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "release_hygiene_scaffold"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    git(base, "init")

    write_text(base / "system-manifest.toml", """schema_version = 1
starter_version = "test"
default_class = "reserved_user"
matching = "specific_before_glob"

[[paths]]
path = "managed.txt"
class = "managed"
content = "text"
""")
    write_text(
        base / "system-lock.toml",
        lockfile_text(
            [
                LockEntry("managed.txt", "managed", "text", "0" * 64),
                LockEntry("seed.md", "scaffold_once", "text", "1" * 64),
            ],
            "test",
            ".",
        ),
    )
    write_text(base / "managed.txt", "managed secret-name\n")
    git(base, "add", ".")

    violations = release_hygiene(base, ["secret-name"], [])

    if "release lockfile contains scaffold-once marker: seed.md" not in violations:
        raise AssertionError(f"expected scaffold lock violation: {violations}")
    if "deny term found in managed.txt: secret-name" not in violations:
        raise AssertionError(f"expected deny-term violation: {violations}")


def test_validate_deny_terms_requires_real_matches() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "release_hygiene_deny_validation"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    git(base, "init")

    write_text(base / "notes.md", "local-product and /local/home/path\n")
    git(base, "add", ".")

    violations = validate_deny_terms(base, ["local-product", "missing-product"], ["/local/home", "missing-regex"])

    expected = {
        "deny term did not match validation tree: missing-product",
        "deny regex did not match validation tree: missing-regex",
    }
    if set(violations) != expected:
        raise AssertionError(f"unexpected deny validation result: {violations}")


def main() -> int:
    test_release_hygiene_rejects_tracked_non_managed_paths()
    test_release_hygiene_rejects_scaffold_lock_entries_and_deny_terms()
    test_validate_deny_terms_requires_real_matches()
    print("release_hygiene tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
