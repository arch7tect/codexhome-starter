# CodexHome

CodexHome is a personal operating context for agent-assisted engineering work. It stores reusable instructions, skills, project profiles, references, wiki notes, and the memory that helps an agent work consistently across repositories.

You normally use this repository by talking to an agent. You should not need to run setup scripts by hand.

## What To Do After Clone

Open this checkout in your agent environment and say:

```text
Initialize this CodexHome instance.
```

If you already know where your project checkouts live, say:

```text
Initialize this CodexHome instance. Use this projects root: <path>.
```

The agent should create the local scaffold files, keep private paths in ignored local config, and tell you what still needs your attention.

## Publish Your Instance

After initialization, create an empty private repository on your preferred host. Then say:

```text
Publish this initialized instance to this private remote: <remote-url>.
```

The agent should keep the clean starter source separate from your private instance, publish only safe initialized files, and refuse to publish local secrets or raw session notes.

## Add Projects

To make a project available for future work, say:

```text
Add this project to CodexHome: <project name>, repository <url>, local path <path>.
```

If the project is unfamiliar, ask the agent to inspect it first:

```text
Inspect this project and create a project profile for future work: <path>.
```

Project profiles help the agent remember where code lives, how to update it, how to verify changes, and what conventions matter.

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

The agent should choose the right workflow, explain the plan, avoid unrelated changes, run suitable checks, and report what changed.

## Preserve Knowledge

When a session produced reusable knowledge, say:

```text
Save the durable learnings from this session.
```

For a raw end-of-session capture, say:

```text
Close this session and save a raw note.
```

The agent should separate rough session notes from durable memory and avoid promoting noise into long-lived context.

## Update CodexHome

To apply new generic starter improvements to an existing private instance, say:

```text
Update this instance from the latest starter release.
```

For a preview first, say:

```text
Show me the starter update plan before applying it.
```

The agent should protect your projects, wiki notes, incidents, local overlays, and private context while updating starter-owned files.

## Read Next

Start with [Getting Started With CodexHome](references/getting-started-with-codexhome.md). It describes the full user journey by use case.

The system is working when you can describe the outcome you want and the agent can handle the mechanics, safety checks, verification, and memory updates.
