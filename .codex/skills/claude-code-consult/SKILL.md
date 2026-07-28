---
name: claude-code-consult
description: Ask the local Claude Code CLI for a bounded read-only second opinion, including reviews spanning multiple repositories. Use when the user explicitly asks to "ask Claude", "ask Claude Code", get a second opinion, or sanity-check an architecture, implementation plan, prompt, test strategy, or code-review conclusion with Claude.
---

# Claude Code Consult

Use this skill to call the local Claude Code CLI as an advisory reviewer. The result is evidence to consider, not an authority. Reconcile Claude's answer with local facts before reporting back.

## Constraints

- Claude Code CLI is optional local tooling. It must already be installed,
  authenticated, and approved for the expected cost on the current machine.
- Default to non-interactive mode only: `-p`.
- Always allow only Claude's read-only repository tools: `Read,Grep,Glob`.
  Do not grant `Bash`, edit, write, notebook, web, or side-effecting tools. When
  command output is needed, collect it separately and include a concise excerpt
  in the prompt.
- Do not let Claude edit files in this skill. If the user explicitly requests a
  Claude-driven editing workflow, handle it separately with explicit scope and
  authorization.
- Do not paste secrets, raw env dumps, API keys, auth headers, or large unredacted logs into Claude.
- Keep the prompt bounded: problem, facts, constraints, exact question, desired output.
- Use the repo root as the working directory unless another cwd is clearly relevant.
- Treat prompt path limits as advisory because `Read` can inspect the working
  directory. Do not run a consultation from a checkout containing plaintext
  credentials or other secrets that Claude must not read.
- Summarize Claude's useful points for the user; do not blindly forward its whole answer if it is long.

## Bundled Runner

Use `scripts/run_consult.py` from this skill. It resolves the CLI from
`$CLAUDE_CODE_CLI` or `PATH`, verifies all required restriction flags, hardcodes
the read-only tool allowlist, applies the cost ceiling, and terminates the child
process after 600 seconds. Resolve the directory containing this loaded
`SKILL.md`, build the absolute path to `scripts/run_consult.py`, and pass that
path directly to Python. Run the helper with `uv` from the repository being
reviewed. Do not assume `$CODEX_HOME` is exported:

```bash
uv run python "<resolved claude-code-consult directory>/scripts/run_consult.py" <<'EOF'
<bounded review prompt>
EOF
```

Replace the placeholder with the resolved path before executing the command.
Do not rewrite this as
`CLAUDE_CONSULT_SKILL_DIR=... uv run python "$CLAUDE_CONSULT_SKILL_DIR/..."`:
the shell expands the path variable before applying the command-scoped
assignment, which can turn the runner path into `/scripts/run_consult.py`.

If the CLI is unavailable or rejects a required restriction flag, stop and
report the failure. Never remove `--tools`, `--permission-mode`, or
`--no-session-persistence` to make the call succeed.

## Multiple Repositories

Use the primary repository as the runner working directory. Grant each
additional repository explicitly with a repeatable `--add-dir` argument:

```bash
uv run python "<resolved runner path>" \
  --add-dir "/path/to/second-repository" \
  --add-dir "/path/to/third-repository" <<'EOF'
<bounded cross-repository review prompt>
EOF
```

The runner resolves every additional path and rejects missing or non-directory
values. It verifies that the installed Claude CLI supports `--add-dir` before
starting the consultation. The Claude tool allowlist remains
`Read,Grep,Glob`.

Do not grant a common parent directory for convenience. Grant only the exact
repository roots needed for the review, list those roots in the prompt, and ask
Claude to report a concrete read marker from every repository before beginning
the review. If any access check fails, stop rather than infer the missing code.

## Standard Call

Use this shape for advisory analysis:

```bash
uv run python "<resolved claude-code-consult directory>/scripts/run_consult.py" <<'EOF'
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

The runner gives each call up to 10 minutes of wall-clock time. Start it as a
yielding process, then poll its session in intervals of no more than 60 seconds
and keep waiting through silence while it is alive. Stop earlier when it exits
or clearly fails. Exit code `124` means the runner terminated it at the
10-minute deadline. Report failures or partial output without retrying with
fewer or broader tools.

The default 10 USD cap is a fixed ceiling and a backstop, not a target. Lower it
with `--max-budget-usd <value>` only when the user explicitly requests a tighter
cost limit. The bundled runner rejects values above 10; changing that fixed
ceiling requires a separately authorized update to this skill.

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
- Asking Claude to re-discover facts that are already known; state them even
  though the read-only tools are available for verification.
- Open-ended prompts like "what do you think?" without constraints.

## Read-Only Scope

Always tell Claude which repository paths it may inspect. For code review,
validation, or incident analysis, narrow the scope to the relevant files and
directly related definitions or tests:

```text
Inspect only these files:
- src/service.py
- tests/test_service.py

Do not edit files. Answer with findings and recommendations only.
```

If Claude cannot use the read-only tools, report the limitation. Do not retry
with broader tools. If Claude names functions, flags, or state that are not
present locally, verify them before treating the finding as a blocker.

## Interpreting Results

When reporting back:

- Separate "Claude suggested" from your own conclusion.
- Keep only high-signal points.
- Challenge suggestions that conflict with local code, replay evidence, or production constraints.
- Turn good suggestions into an actionable next step: config change, code change, replay fixture, metric, or prompt update.
