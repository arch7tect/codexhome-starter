---
name: claude-code-consult
description: Ask the local Claude Code CLI for a bounded second opinion from inside an agent workflow. Use when the user explicitly asks to "ask Claude", "ask Claude Code", get a second opinion, or sanity-check an architecture, implementation plan, prompt, test strategy, or code-review conclusion with Claude.
---

# Claude Code Consult

Use this skill to call the local Claude Code CLI as an advisory reviewer. The result is evidence to consider, not an authority. Reconcile Claude's answer with local facts before reporting back.

## Constraints

- Claude Code CLI is optional local tooling. It must already be installed,
  authenticated, and approved for the expected cost on the current machine.
- Default to non-interactive mode only: `-p`.
- Default to no Claude tools: `--tools ""`. Pass concise context yourself.
- Do not let Claude edit files unless the user explicitly asks for that workflow.
- Do not paste secrets, raw env dumps, API keys, auth headers, or large unredacted logs into Claude.
- Keep the prompt bounded: problem, facts, constraints, exact question, desired output.
- Use the repo root as the working directory unless another cwd is clearly relevant.
- Summarize Claude's useful points for the user; do not blindly forward its whole answer if it is long.

## CLI Path

Resolve the CLI once before calling it. Prefer `$CLAUDE_CODE_CLI` when it is
set, then fall back to `PATH`:

```bash
CLAUDE="${CLAUDE_CODE_CLI:-}"
if [ -z "$CLAUDE" ]; then
  CLAUDE="$(command -v claude || true)"
fi
if [ -z "$CLAUDE" ]; then
  echo "Claude Code CLI is unavailable in this shell" >&2
  exit 1
fi
"$CLAUDE" --version
```

If resolution fails, report that Claude Code CLI is unavailable in this shell.

## Standard Call

Use this shape for advisory analysis:

```bash
"$CLAUDE" \
  -p \
  --no-session-persistence \
  --permission-mode dontAsk \
  --tools "" \
  --max-budget-usd 2 <<'EOF'
You are reviewing a technical decision. Do not edit files.

Context:
- <facts>

Constraints:
- <what cannot change>

Question:
- <specific question>

Please be concrete and skeptical. Highlight risks and tradeoffs.
EOF
```

Poll the command until it exits. If it produces no output for about 90 seconds, check whether the process is still alive. If it appears stuck on auth, permission, or network, stop and report the blocker.

## Prompt Checklist

Include:

- The current task and why Claude is being consulted.
- Hard constraints, especially things that cannot be changed.
- Concrete evidence: file paths, line references, session ids, metrics, thresholds, or short log excerpts.
- What you want back: architecture, prompt, test plan, risk list, or critique.
- Any output constraints: "no code edits", "public API cannot change", "must stay backward compatible", "low latency".

Avoid:

- Full raw logs when a short excerpt or summary is enough.
- Credentials and redacted-but-still-sensitive config blocks.
- Asking Claude to re-discover facts that are already known unless tools are intentionally enabled.
- Open-ended prompts like "what do you think?" without constraints.

## Optional Read-Only Inspection

Only if the user explicitly wants Claude to inspect local files, allow read-only tools and tightly constrain the scope:

```bash
"$CLAUDE" \
  -p \
  --no-session-persistence \
  --permission-mode dontAsk \
  --tools "Read,Grep,Glob" \
  --max-budget-usd 3 <<'EOF'
Inspect only these files:
- src/service.py
- tests/test_service.py

Do not edit files. Answer with findings and recommendations only.
EOF
```

If Claude reports it cannot use those tools, fall back to the standard call and paste concise excerpts.

## Interpreting Results

When reporting back:

- Separate "Claude suggested" from your own conclusion.
- Keep only high-signal points.
- Challenge suggestions that conflict with local code, replay evidence, or production constraints.
- Turn good suggestions into an actionable next step: config change, code change, replay fixture, metric, or prompt update.
