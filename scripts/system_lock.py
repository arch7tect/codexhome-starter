from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal


ContentType = Literal["text", "binary"]
PathClass = Literal["managed", "scaffold_once", "reserved_user"]
Disposition = Literal["apply", "noop", "report", "stop"]


@dataclass(frozen=True)
class LockDecisionInput:
    baseline_hash: str | None
    local_hash: str | None
    starter_hash: str | None
    locked_class: PathClass = "managed"
    manifest_class: PathClass = "managed"
    locked_content_type: ContentType = "text"
    manifest_content_type: ContentType = "text"


@dataclass(frozen=True)
class LockDecision:
    action: str
    disposition: Disposition
    reason: str


def normalize_text_bytes(data: bytes) -> bytes:
    text = data.decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n") + "\n"
    return text.encode("utf-8")


def normalized_bytes(data: bytes, content_type: ContentType) -> bytes:
    if content_type == "text":
        return normalize_text_bytes(data)
    if content_type == "binary":
        return data
    raise ValueError(f"unsupported content type: {content_type}")


def normalized_sha256(data: bytes, content_type: ContentType) -> str:
    return sha256(normalized_bytes(data, content_type)).hexdigest()


def file_sha256(path: Path, content_type: ContentType) -> str:
    return normalized_sha256(path.read_bytes(), content_type)


def decide_lock_action(state: LockDecisionInput) -> LockDecision:
    if state.locked_class != state.manifest_class:
        return LockDecision("stop_class_change", "stop", "path class changed between lockfile and manifest")

    if state.locked_content_type != state.manifest_content_type:
        return LockDecision("stop_content_type_change", "stop", "content type changed between lockfile and manifest")

    baseline = state.baseline_hash
    local = state.local_hash
    starter = state.starter_hash

    if baseline is None:
        if starter is None:
            if local is None:
                return LockDecision("noop", "noop", "path is absent locally and absent from starter")
            return LockDecision("keep_local", "report", "path exists locally but is absent from lockfile and starter")
        if local is None:
            return LockDecision("safe_new", "apply", "starter adds a managed file that is absent locally")
        return LockDecision("conflict_existing_untracked", "stop", "starter adds a managed path that already exists locally")

    if starter is None:
        if local is None:
            return LockDecision("noop_removed", "noop", "starter removed the path and it is absent locally")
        if local == baseline:
            return LockDecision("prune_candidate", "report", "starter removed an unchanged managed file")
        return LockDecision("keep_local", "report", "starter removed the file but local content changed")

    if local is None:
        return LockDecision("stop_local_deleted", "stop", "local deleted a managed file that starter still contains")

    if local == starter:
        if local == baseline:
            return LockDecision("noop", "noop", "local, starter, and lockfile hashes match")
        return LockDecision("noop_update_lock", "report", "local and starter converged to identical content")

    if local == baseline:
        return LockDecision("fast_forward", "apply", "local is unchanged and starter changed")

    if starter == baseline:
        return LockDecision("keep_local", "report", "local changed and starter did not change")

    return LockDecision("conflict", "stop", "local and starter both changed differently")
