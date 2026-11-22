# 2026-11-03: does Claude Code 2.1.311 keep what the fleet relies on from 2.1.286?

**Why.** The owner moved the fleet to Claude Code's npm stable on 2026-11-03 (job j560). The target was 2.1.311, because npm's `stable` tag had moved there from 2.1.309. The pin in `runtime/claude-code/harness.json` was 2.1.286. Five claims the fleet builds on had been read back only on other builds, so each one was read back on 2.1.311 before the pin moved:
- the worktree import approval (`2026-10-20-worktree-include-approval.md`);
- what `--system-prompt-file` replaces (read on 2.1.274);
- the shape of subagent transcripts;
- the managed hooks (N3, N9, N11a, N11b in `2026-10-31-managed-settings-2-1-316.md`), read on 2.1.316 only, a build newer than the target;
- the second run of the dispatch guard (`2026-11-02-dispatch-hook-reruns-on-updated-input.md`, which asks to be read back when the pin moves).

ADR-043 rule 6 is the gate for the move itself.

**How.** The trial ran on user@develop-qzapp, which was brought to 2.1.311 with `fabric-ctl user upgrade claude --version 2.1.311`; this session ran on it, under a fabric launch (the launcher's pins, `AGENT_FABRIC_LAUNCH_PROVIDER=anthropic`), and stream-json `init` reports `2.1.311` in every child run below. Child sessions ran `claude -p` on the 2.1.311 binary with only the login's setup token added to their environment, and the model was haiku. A child that runs Bash had `XDG_STATE_HOME` pointed at an empty folder. The reason: the job-copy guard reads the login's active job, and its deny (this session's job, outside its copy) otherwise answers before the guard under test. Scratch folders lived in the session's scratchpad. No commit was made anywhere: the repositories used are empty or hold an orphan worktree.

**Measured on develop-qzapp, 2026-11-03, 2.1.311:**

| case | what ran | result |
|---|---|---|
| N9 control | Bash `git status --short \| wc -l` in an empty repository | ran, printed 0 |
| N9 | Bash `false \| tail -1 && git commit --allow-empty -m probe`, the managed file in force, no pipe-status hook in user or project settings | denied with the pipe-status reason; the repository still has no commit. The managed exec-form hook (`command` + `args`) runs with its args |
| N2, N3 | `fabric-managed probe` | ok: `agent-dispatch-guard` denies a class dispatch with no model; `claude --plugin-dir` exits 1 under `disableSideloadFlags` |
| N11 control | project-scope exec-form hook, a script that prints a deny | denied with the script's reason |
| N11a | project-scope exec-form hook: `/usr/local/bin/fabric-python` on a missing script | `fabric-python` exits 2 ("can't open file") and the call is blocked: fails closed |
| N11b | project-scope exec-form hook: a missing interpreter | spawn fails, and **the command ran**: fails open |
| R1 | the 2026-10-20 fixture, approval on: neither / main checkout / worktree / both | invariant line: absent / quoted / absent / quoted. Claude Code wrote nothing to either entry |
| R2 | request bodies to a loopback listener (dummy API key; it answered 400): default, `--system-prompt-file`, `--append-system-prompt-file` | see below |
| R3 | an `Explore` subagent dispatched from this session | see below |
| D1 control | `code-review` dispatch, `model: fable`, no `run_in_background` | allowed; `code-review.md` opened twice: one guard run on its allow path |
| D2 | the same with `run_in_background: true` | allowed; `code-review.md` opened four times, two in each of two guard runs |

**R2, what the system prompt holds.** Each request had three system blocks: the billing header, an opening line, and the body. With `--system-prompt-file` the body is the file's text alone (46 bytes against 8,443), and the memory section is gone. The opening line stays `You are a Claude agent, built on Anthropic's Claude Agent SDK.`, all 12 tool schemas are sent, the agent listing is in the Agent tool's schema, and CLAUDE.md arrives in the first user turn. With `--append-system-prompt-file` the default body is kept and the file follows it. That case's opening line is `You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK.`, which differs from the other two cases. 2.1.311 replaces what 2.1.274 replaced.

**R3, the subagent transcript.** `subagents/agent-<id>.jsonl` sits beside `agent-<id>.meta.json`, whose `agentType` is `Explore`. The sidecar now also carries `isBuiltIn`, `description`, `toolUseId`, `spawnDepth`, `requestShape`, `requestNonInteractive`, `model` and `finished`. The transcript holds one `Read` and the hand-back as a `tool_use` named `SubagentHandback`. One of its four user records carries a `<system-reminder>`. The transcript is shaped as on 2.1.286.

**D1, D2.** Other accounts on the host share the snapshot, so `dispatch_guard.py` opens arrive at random. The runs were counted by `~/.claude/agents/code-review.md`, which only this login reads and which the guard opens only on its allow path. With `run_in_background` 2.1.311 still runs the managed Agent hook a second time, on the first run's `updatedInput`. Since #458 the guard accepts its own answer, so both runs allow and the dispatch goes ahead.

**What it decides.**
- Each claim holds on 2.1.311, N11a and N11b at project scope only (Not measured, below). Nothing the fleet does changes for the move.
- N11b stays the case the check covers. A managed guard whose interpreter is missing is off, and the workspace copies stand down only while `/usr/local/bin/fabric-python` is executable.
- ADR-043 rule 6 is met. `fabric-ctl all status` reported `managed in force` on each of its 30 rows, all on develop-qzapp, the registry's only host (`runtime/hosts/registry.json`). `fabric-managed check --json` said `"state": "in force"` for snapshot `1853a2d11b703c1191c9d6a84677cf7a51eaa99a`, and `fabric-managed probe` passed on 2.1.311. The pin moves to 2.1.311.
- The merge itself takes the host out of force. The snapshot holds `runtime/` and `policies/`, which this change edits, so after it lands `fabric-managed check` reads `drifted`, and `fabric-ctl <login> upgrade claude` refuses any build at or above 2.1.287 until the managed settings are in force again (`tools/fabric/control/upgrade.py`, `managed_gate`). The order after the merge is therefore: the operator runs `sudo fabric-managed install --sha <main after the merge>` (rule 9), then `fabric-ctl all upgrade fabric`, then `fabric-ctl all upgrade claude`.

**Not measured here.**
- N11a and N11b with the hook in `/etc/claude-code/managed-settings.json`. That needs root (the 2026-10-31 private mount namespace), and on 2.1.316 it gave the same two results. These runs put the same exec-form shape at project scope, which runs through the same spawn path but is not the managed tier.
- An interactive session's approval dialog, and an interactive session's trust question in a worktree (as on 2026-10-20).
- Any account but user. The other 29 move in the order above, after the pin merges.
