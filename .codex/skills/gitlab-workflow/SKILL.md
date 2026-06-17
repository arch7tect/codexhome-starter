---
name: gitlab-workflow
description: Manage generic GitLab repository workflows with glab. Use when the user asks to inspect GitLab remotes, create or update merge requests, check MR status, inspect GitLab pipelines, push a branch for GitLab review, comment on an MR, or merge a GitLab MR.
---

# GitLab Workflow

Use this skill for GitLab work through `git` and `glab`: repository inspection, branch push, merge request creation, MR status, pipeline checks, comments, and guarded merges.

Do not use this skill for GitHub pull requests or provider-neutral initialized instance publishing. Read `references/system/git-host-workflow-policy.md` before acting.

## Rules

- Never print tokens, auth headers, credential helper output, or raw auth config files.
- Use `glab auth status` for auth checks. If auth is missing or configured for the wrong host, ask the user to configure it locally.
- Do not use force push or history rewrite commands unless the user explicitly asks for that exact operation.
- Do not stage unrelated files. In a dirty worktree, inspect changed paths and stage only the intended files.
- Creating an MR and merging an MR are separate operations. Merge only after a direct user request.
- Prefer draft MRs unless the user asks for a ready MR.
- If the repository remote is not GitLab, stop and report that this skill does not apply.
- If the current checkout is CodexHome, confirm whether the user means the CodexHome instance or an external project repository. Use this skill only for project merge requests.

## Preflight

1. Resolve the repository root.
2. Inspect `git status --short`, current branch, and `git remote -v`.
3. Confirm a GitLab remote is present.
4. Run `command -v glab`, `glab --version`, and `glab auth status`.
5. Fetch remote refs before relying on local branch state when the worktree is clean enough to do so safely.
6. Determine the target branch from the user request or the upstream default branch. If the target equals the source branch, stop and ask for the intended target.

If `glab` is missing or unauthenticated, stop with one actionable setup sentence. When useful, offer a Git-only fallback: push the branch and tell the user to open the merge request in GitLab.

## Branch And Commit

For a direct request to push without asking for an MR, prefer the current project branch and its upstream. Create a new branch only when the user asks for an MR or new branch, the current branch is unsuitable, or pushing the current branch would mix unrelated work.

Before committing:

```bash
git diff --stat
git status --short
```

Use the repository's commit message convention. If none is known, use a short one-line message without tool attribution.

## Push

For a push request, push the current branch to the expected GitLab remote after verifying the branch and intended commits. If the branch has no upstream, use `git push -u origin <branch>`.

If `glab` auth is configured for a different GitLab host but plain Git push to `origin` works and no MR/API action is required, proceed with Git push and report that API actions were skipped because CLI auth is not configured for the remote host.

## Create Or Update MR

Before creating an MR, check whether one already exists for the current branch:

```bash
glab mr list --source-branch <branch> --output json
```

If an MR already exists, report its URL and do not create a duplicate.

Create a draft MR unless the user requested ready for review:

```bash
glab mr create --draft --fill --yes --source-branch <branch> --target-branch <target-branch>
```

Use an explicit title and description when `--fill` would be weak or misleading.

## Inspect MR And Pipelines

Use:

```bash
glab mr view <iid-or-branch> --output json
glab mr view <iid-or-branch> --comments
glab mr view <iid-or-branch> --unresolved
glab mr diff <iid-or-branch>
glab ci status --branch <branch> --output json
```

Summarize status, failing jobs, unresolved discussions, and any required user decision.

## Comments

Before posting comments, show or summarize the intended comment unless the user already provided exact text.

```bash
glab mr note <iid-or-branch> -m "<comment>"
```

## Merge Guard

Merge only when the user explicitly asks. Before merging, verify:

- MR is not draft unless the user explicitly accepts that state.
- Target branch is expected.
- The source branch is not the protected/default branch by mistake.
- Current local HEAD matches the MR source branch when local state matters.
- Required pipelines and approvals are passing, or the user explicitly accepts the risk.
- Unresolved discussions are handled or explicitly accepted.
- GitLab does not report conflicts.
- Branch protection is respected; do not bypass protections or merge with failing required checks unless the user explicitly accepts an allowed repository policy path.

Collect enough state to merge deliberately:

```bash
glab mr view <iid-or-branch> --output json
glab mr view <iid-or-branch> --unresolved
glab mr approvers <iid-or-branch>
glab ci status --branch <branch> --output json
git fetch origin
git status --short
git rev-parse HEAD
```

Use `glab mr merge` with the current source SHA and the merge mode requested by the user. If no mode is requested, use the repository default or ask when ambiguous.

## Final Response

Keep the final response short. Report the branch, MR URL, draft or ready state, commit hash if created, pipeline status, merge result if merged, skipped checks or blockers, and any remaining risk. Keep secrets and tokens out of the response.
