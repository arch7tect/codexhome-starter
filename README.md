# CodexHome

CodexHome is a personal operating context for agent-assisted engineering work. It stores reusable instructions, skills, project profiles, references, wiki notes, and the memory that helps an agent work consistently across repositories.

You normally use this repository by talking to an agent. You should not need to run setup scripts by hand.

Want the full picture first? Read [Getting Started With CodexHome](references/getting-started-with-codexhome.md).

## Before You Start

You need an AI coding agent that can read and edit files in this cloned folder. Point the agent at this checkout, then give it the plain-language instructions below.

If the agent cannot complete a step, ask it to explain the blocker, what changed, and what decision it needs from you.

## What To Do After Clone

Say:

```text
Initialize this CodexHome instance.
```

If you already know where your project checkouts live, say:

```text
Initialize this CodexHome instance. Use this projects root: <path>.
```

Expect local scaffold files, ignored private config, and a short summary of anything still needing your input.

## Publish Your Instance

After initialization, create an empty private repository on your preferred host. Then say:

```text
Publish this initialized instance to this private remote: <remote-url>.
```

Use the private repository URL from GitHub, GitLab, or another host. Expect the agent to keep the clean starter source separate from your private instance, publish only safe initialized files, and refuse to publish local secrets or raw session notes.

## Add Projects

To make a project available for future work, say:

```text
Add this project to CodexHome: <project name>, repository <url>, local path <path>.
```

The local path should point to the project checkout on your machine.

If the project is unfamiliar, ask the agent to inspect it first:

```text
Inspect this project and create a project profile for future work: <path>.
```

Expect a project profile that records where code lives, how to update it, how to verify changes, and what conventions matter.

## Work With Projects

Once a project is registered, stay at the level of intent:

```text
In <project>, fix <problem> and verify it.
```

```text
Review the current changes in <project> for bugs and missing tests.
```

```text
Create a GitHub pull request for the current branch.
```

```text
Create a GitLab merge request for the current branch.
```

```text
Resolve the merge conflicts for this project branch.
```

Expect the agent to choose the right workflow, explain the plan, avoid unrelated changes, run suitable checks, and report what changed.

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

Expect the agent to keep raw notes separate from durable wiki pages, link related pages, verify wiki health, and ask before promoting uncertain knowledge.

## Preserve Knowledge

When a session produced reusable knowledge, say:

```text
Save the durable learnings from this session.
```

For a raw end-of-session capture, say:

```text
Close this session and save a raw note.
```

Expect the agent to separate rough session notes from durable memory and avoid promoting noise into long-lived context.

## Update CodexHome

To apply new generic starter improvements to an existing private instance, say:

```text
Update this instance from the latest starter release.
```

For a preview first, say:

```text
Show me the starter update plan before applying it.
```

Expect the agent to protect your projects, wiki notes, incidents, local overlays, and private context while updating starter-owned files.

## Read Next

Use [Getting Started With CodexHome](references/getting-started-with-codexhome.md) as the detailed user journey by use case.

The system is working when you can describe the outcome you want and the agent can handle the mechanics, safety checks, verification, and memory updates.
