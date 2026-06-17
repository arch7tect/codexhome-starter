---
name: github-workflow
description: Manage generic GitHub repository workflows with gh. Use when the user asks to inspect GitHub remotes, create or update pull requests, check PR status, inspect GitHub Actions, push a branch for GitHub review, comment on a PR, or merge a GitHub PR.
---

# GitHub Workflow

Use this skill for GitHub work through `git` and `gh`: repository inspection, branch push, pull request creation, PR status, GitHub Actions checks, comments, and guarded merges.

Do not use this skill for GitLab merge requests or provider-neutral initialized instance publishing. Read `references/system/git-host-workflow-policy.md` before acting.

## Rules

- Never print tokens, auth headers, credential helper output, or raw auth config files.
- Use `gh auth status` for auth checks. If auth is missing, ask the user to configure it locally.
- Do not use force push or history rewrite commands unless the user explicitly asks for that exact operation.
- Do not stage unrelated files. In a dirty worktree, inspect changed paths and stage only the intended files.
- Creating a PR and merging a PR are separate operations. Merge only after a direct user request.
- Prefer draft PRs unless the user asks for a ready PR.
- If the repository remote is not GitHub, stop and report that this skill does not apply.
- If the current checkout is CodexHome, confirm whether the user means the CodexHome instance or an external project repository. Use this skill only for project pull requests.

## Preflight

1. Resolve the repository root.
2. Inspect `git status --short`, current branch, and `git remote -v`.
3. Confirm a GitHub remote is present.
4. Run `command -v gh`, `gh --version`, and `gh auth status`.
5. Fetch remote refs before relying on local branch state when the worktree is clean enough to do so safely.

If `gh` is missing or unauthenticated, stop with one actionable setup sentence. When useful, offer a Git-only fallback: push the branch and tell the user to open the pull request in GitHub.

## Push

For a push request, push the current branch to the expected GitHub remote after verifying the branch and intended commits. If the branch has no upstream, use `git push -u origin <branch>`.

## Create Or Update PR

Before creating a PR, check whether one already exists for the current branch:

```bash
gh pr list --head <branch> --json number,url,state,title,isDraft
```

Create a draft PR unless the user requested ready for review:

```bash
gh pr create --draft --fill --base <target-branch> --head <branch>
```

Use an explicit title and body when `--fill` would be weak or misleading.

## Inspect PR And Checks

Use:

```bash
gh pr view <number-or-branch> --json number,title,url,state,isDraft,baseRefName,headRefName,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <number-or-branch>
gh run list --branch <branch> --limit 10
```

Summarize status, failing checks, and any required user decision.

## Comments

Before posting comments, show or summarize the intended comment unless the user already provided exact text.

```bash
gh pr comment <number-or-branch> --body "<comment>"
```

## Merge Guard

Merge only when the user explicitly asks. Before merging, verify:

- PR is not draft unless the user explicitly accepts that state.
- Target branch is expected.
- The source branch is not the protected/default branch by mistake.
- Current local HEAD matches the PR head when local state matters.
- Required checks and reviews are passing, or the user explicitly accepts the risk.
- There are no unresolved requested changes.
- Branch protection is respected; do not bypass protections or merge with failing required checks unless the user explicitly accepts an allowed repository policy path.

Prefer `gh pr merge` with the merge mode requested by the user. If no mode is requested, use the repository default or ask when ambiguous.

## Final Response

Report the branch, PR URL, check status, action taken, and any remaining risk. Keep secrets and tokens out of the response.
