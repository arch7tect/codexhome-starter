# Git Host Workflow Policy

This policy is shared by generic GitHub and GitLab repository workflow skills.

## Scope

Use Git host workflow skills for external project repositories: branch push, pull or merge request creation, review status, CI or pipeline status, comments, and explicit merge requests.

Do not use Git host workflow skills to publish a CodexHome instance. Instance publishing is provider-neutral and uses the initialized instance publishing workflow.

## Preconditions

Before using provider CLIs:

1. Confirm the repository root and remote URL.
2. Confirm the requested action targets the intended repository, especially when the current checkout is CodexHome rather than an external project.
3. Confirm the provider CLI exists: `gh` for GitHub or `glab` for GitLab.
4. Confirm provider CLI authentication without printing tokens or config files.
5. If the provider CLI is missing or unauthenticated, stop with one actionable setup sentence and offer a Git-only fallback when useful.

## Provider Detection

Support common hosted and enterprise remote shapes:

- GitHub: `github.com`, `github.<company>`, `github-<company>`, and remotes already recognized by `gh`.
- GitLab: `gitlab.com`, `gitlab.<company>`, `gitlab-<company>`, and remotes already recognized by `glab`.

If the host is ambiguous, ask before acting. If the repository is another provider, do not force GitHub or GitLab behavior.

## Fallback

When `gh` or `glab` cannot be used, do not invent API calls. Safe fallback options are:

- push the branch with plain Git when the user asked to push;
- report the branch and remote URL;
- suggest opening a pull or merge request in the host UI;
- print a compare URL only when the host pattern is clear.

## Merge Guard

Merging requires a fresh explicit user request in the current turn. Never infer merge permission from a request to create or inspect a pull or merge request.

Before merging:

- verify the target branch is expected and is not accidentally the default branch as a source;
- verify the local source branch and remote PR/MR head match when local state matters;
- verify required checks, pipelines, approvals, and unresolved discussions;
- respect protected branch rules and do not override them;
- stop on ambiguity and ask the user.

Do not use force push or history rewriting unless the user explicitly asks for that exact operation.

## Conflict Resolution Boundary

GitHub and GitLab workflow skills detect provider-reported conflicts, report the affected pull or merge request, and re-check provider status after a branch is updated.

Local conflict mechanics are provider-neutral. When a pull or merge request reports conflicts, use `$merge-conflict-resolution` to inspect the local repository, resolve merge, rebase, cherry-pick, or stash-pop conflicts, run project verification, and prepare the branch for provider re-check.

Conflict resolution must preserve unrelated local changes, avoid broad ours/theirs strategy shortcuts, resolve per hunk and per intent, and stop for a user decision when the correct behavior is ambiguous.
