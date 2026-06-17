# Getting Started With CodexHome

This guide is for the person using CodexHome with an agent. Work by use case: say what outcome you want, review the plan, and approve the next step when the agent asks.

CodexHome is not an application project. It is the operating context for agent-assisted work: reusable instructions, skills, project profiles, wiki notes, references, and repository memory.

## Mental Model

CodexHome has two layers:

- Starter: generic system mechanics that can be updated for every installation.
- Instance: your private working memory, project profiles, local notes, and organization-specific knowledge.

Your job is to decide what should happen and what is safe to keep. The agent's job is to run the right workflow, use the right skill, avoid publishing local secrets, and explain what changed.

## First Day

After cloning the starter, say:

```text
Initialize this CodexHome instance.
```

If you already know where your project checkouts live, say:

```text
Initialize this CodexHome instance. Use this projects root: <path>.
```

When the instance is initialized, publish it to your private Git repository:

```text
Publish this initialized instance to this private Git remote: <git-url>.
```

Use a GitHub, GitLab, or other Git remote URL. The remote repository should already exist, be private, and be empty.

This publishes your CodexHome instance. It is different from opening a pull request or merge request for a project.

## Add Projects

To add a codebase you want the agent to work with, say:

```text
Add this project to CodexHome: <project name>, repository <url>, local path <path>.
```

If you want the agent to inspect the project before saving a profile, say:

```text
Inspect this project and create a project profile for future work: <path>.
```

The project profile should make future work easier: where the code lives, how to update it, how to run checks, and what risks or conventions matter.

## Work On A Task

For normal engineering work, say the outcome and the project:

```text
In <project>, fix <problem> and verify it.
```

For a planned change:

```text
In <project>, design the change for <feature or refactor> before editing code.
```

For a review:

```text
Review the current changes in <project> for bugs and missing tests.
```

The agent should read the relevant project profile, use the matching skill, inspect the code before editing, run suitable checks, and report what changed.

## GitHub And GitLab

Generic GitHub and GitLab workflows are available out of the box.

Use these phrases when you are inside an external project repository or when you name the project. They are for project changes, not for publishing the CodexHome instance.

For GitHub, say:

```text
Create a GitHub pull request for the current branch.
```

or:

```text
Check the GitHub pull request status and CI.
```

For GitLab, say:

```text
Create a GitLab merge request for the current branch.
```

or:

```text
Check the GitLab merge request status and pipeline.
```

The agent should use the repository remote to choose GitHub or GitLab behavior, avoid exposing tokens, and ask before merging.

These workflows need the matching local Git host tool to be installed and authenticated. If it is missing, the agent should say what to configure and offer a safe fallback such as pushing the branch.

When a pull request or merge request has conflicts, say:

```text
Resolve the merge conflicts for this project branch.
```

or:

```text
Resolve the conflicts reported by this GitHub pull request: <details>.
```

or:

```text
Resolve the conflicts reported by this GitLab merge request: <details>.
```

## Investigate An Incident

For an incident, give the project or system name and the symptom:

```text
Investigate this incident: <link, id, screenshot, or symptom>.
```

If there are logs or artifacts:

```text
Investigate this incident using these artifacts: <paths or links>.
```

The agent should create or use a case workspace, keep raw artifacts out of committed memory, collect evidence, and produce a concise report with root cause, impact, and next steps.

## Build The Wiki

The wiki is where durable, reusable knowledge becomes linked context instead of scattered session notes. Use it for concepts, decisions, workflows, project maps, and lessons that should help future work.

After meaningful project work, say:

```text
Extract durable wiki knowledge from this session.
```

For a known topic, say:

```text
Create or update a wiki page for <topic>.
```

To keep the knowledge base healthy, say:

```text
Review the wiki for stale, duplicate, or conflicting pages.
```

The agent should keep raw notes separate from durable wiki pages, link related pages, verify wiki health, and ask before promoting uncertain knowledge.

## Save Knowledge

After a useful task, ask the agent to preserve what should help future work:

```text
Save the durable learnings from this session.
```

If you only want a raw capture:

```text
Close this session and save a raw note.
```

The agent should separate raw notes from durable memory. Not every session should become permanent knowledge.

For structured, reusable knowledge that should become linked context, use the wiki workflow above.

## Update From Starter

When you want the latest generic CodexHome improvements, say:

```text
Update this instance from the latest starter release.
```

If you want to see the impact first, say:

```text
Show me the starter update plan before applying it.
```

The agent should protect your instance-owned projects, wiki notes, incidents, and local context while applying starter-owned updates.

## Publish Or Push Changes

To push your private instance after ordinary local changes, say:

```text
Commit and push the current intended CodexHome changes.
```

To publish a newly initialized instance, use the first-day phrase instead:

```text
Publish this initialized instance to this private Git remote: <git-url>.
```

The agent should never publish `.env`, raw session notes, temporary files, or local-only artifacts.

## What To Ask Next

Use these phrases as your main control surface:

- `Initialize this CodexHome instance.`
- `Publish this initialized instance to this private Git remote: <git-url>.`
- `Add this project to CodexHome: <name>, repository <url>, local path <path>.`
- `In <project>, fix <problem> and verify it.`
- `Review the current changes in <project>.`
- `Investigate this incident: <details>.`
- `Extract durable wiki knowledge from this session.`
- `Create or update a wiki page for <topic>.`
- `Review the wiki for stale, duplicate, or conflicting pages.`
- `Save the durable learnings from this session.`
- `Close this session and save a raw note.`
- `Update this instance from the latest starter release.`
- `Create a GitHub pull request for the current branch.`
- `Create a GitLab merge request for the current branch.`
- `Check the GitHub pull request status and CI.`
- `Check the GitLab merge request status and pipeline.`
- `Resolve the merge conflicts for this project branch.`

The system is working when you can stay at the level of intent and the agent can explain the plan, safety checks, changed files, and verification results.
