# CodexHome

CodexHome is a personal operating context for agent-assisted engineering work. It stores reusable instructions, skills, project profiles, wiki notes, references, and the memory that helps an agent work consistently across repositories.

You normally use this repository by talking to an agent. You should not need to run setup scripts by hand.

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

## What's Inside

- `projects/` stores profiles for codebases the agent should understand.
- `wiki/` stores linked durable knowledge: concepts, decisions, workflows, project maps, and lessons.
- `.codex/skills/` stores reusable agent procedures.
- `references/` stores longer guides, background material, and system documents.
- Local scaffold files store private instance context without copying it into the clean starter.

## Where To Go Next

Use [Getting Started With CodexHome](references/getting-started-with-codexhome.md) as the canonical user journey. It covers adding projects, working on tasks, GitHub and GitLab workflows, building the wiki, investigating incidents, preserving knowledge, publishing instance changes, and updating from the starter.

The system is working when you can describe the outcome you want and the agent can handle the mechanics, safety checks, verification, and memory updates.
