---
name: merge-conflict-resolution
description: Resolve local Git merge, rebase, cherry-pick, or stash-pop conflicts safely. Use when the user asks to resolve conflicts, a GitHub PR or GitLab MR reports conflicts, or a local Git operation stops on conflicts.
---

# Merge Conflict Resolution

Use this skill for provider-neutral local conflict mechanics. GitHub and GitLab workflow skills may detect conflicts in a pull or merge request, but local conflict resolution belongs here.

## Rules

- Preserve unrelated local changes. Do not start a conflict-producing operation from a dirty worktree unless the user explicitly approves how to protect the existing changes.
- If the repository is already in a conflict state, inspect the status and separate conflicted paths from unrelated local edits before touching files. Stop if unrelated edits make the resolution unsafe.
- Do not use force push or history rewrite commands unless the user explicitly asks for that exact operation.
- Do not default to broad strategy shortcuts such as `-X ours`, `-X theirs`, whole-file `--ours`, or whole-file `--theirs`.
- Resolve per file and per hunk according to intent. Use one side wholesale only when the file's semantics make that decision clear.
- Do not auto-stash, abort, or discard work without explicit user approval.
- Run project-specific verification from the relevant project profile or repository docs. Do not hardcode generic test commands when the project has its own verification contract.

## Preflight

1. Resolve the repository root and read the relevant project profile when available.
2. Identify the operation: merge, rebase, cherry-pick, stash-pop, or provider-reported PR/MR conflict.
3. Identify the source branch, target branch, current branch, and intended final state.
4. Inspect `git status --short`, branch state, and recent commits.
5. Fetch remote refs only when it can be done without disturbing local work.

If the worktree is dirty before starting a new merge, rebase, or cherry-pick, stop and ask how to handle the existing changes. Safe choices include committing them, moving them to a separate branch, or stashing them with explicit approval.

## Resolution Lifecycle

1. Inspect conflicted paths with status and diff commands.
2. Understand base, current side, and incoming side before editing. Enable diff3 or zdiff3 conflict style when it helps explain the base.
3. Resolve each conflicted hunk deliberately. Preserve both changes when they are compatible.
4. Re-run status and diff review after edits.
5. Run the smallest meaningful project verification, then broader checks when the conflict touched shared behavior.
6. Stage only resolved, intended files.
7. Continue the original operation: complete the merge commit, continue the rebase, continue the cherry-pick, or finish the stash-pop cleanup.
8. Re-run verification after the operation completes.
9. If the conflict came from a GitHub PR or GitLab MR, hand back to the provider workflow skill to push the branch and re-check provider status.

## Abort Path

When resolution is unsafe, behavior is unclear, or the user asks to stop, explain the state and use the matching abort path only after confirming the effect:

- merge: abort the merge;
- rebase: abort the rebase;
- cherry-pick: abort the cherry-pick;
- stash-pop: reset only with explicit approval, because stash-pop has no exact abort command.

If any resolved work should be preserved before aborting, save it in an explicit patch or branch only with user approval.

## Semantic Conflicts

Text conflicts can hide behavioral conflicts. Escalate to the user when both sides compile but the intended behavior, data migration, public contract, or product decision is ambiguous.

## Final Response

Report the operation, resolved files, important intent decisions, verification commands and results, whether changes were pushed, and any provider follow-up still needed.
