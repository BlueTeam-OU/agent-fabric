# ADR-043 — Claude Code mods: managed only, the guards in managed settings, the fleet's mods from a root-owned marketplace

**Date:** 2026-10-04
**Status:** Accepted
**Ratified:** owner, 2026-10-05, by the merge of agent-fabric #97 (6f58bf7d), which carried it, as §8 provided
**Decision Makers:** the owner (asked for this record after reading the mods announcement); drafted by fabric-coordinator
**Scope:** each host's `/etc/claude-code/managed-settings.json`, the fleet's guards (the `PreToolUse` and `PreModelSwitch` hooks now registered in the workspace's `.claude/settings.json`), the fleet's own mods, and the Claude Code pin in `runtime/claude-code/harness.json`
**Pillar:** P1

## 1. Context and Problem

Claude Code has mods: plugins whose JavaScript or TypeScript handlers run inside Claude Code's own process, on by default in 2.1.287 and later. A handler hooks an event (a tool call, a prompt, a turn, a piece of the interface) and observes it, rewrites it, or answers it in the built-in behaviour's place. They are not sandboxed: a mod runs as its login, reads that login's environment and settings, sees every prompt and tool call, and can approve a tool call before a permission prompt appears. Claude can write a mod, install it and hot-reload it within one session.

The fleet's authority rests on guards (ADR-005, ADR-018, ADR-020): the dispatch guard, the subagent clone guard, the pipe-status guard, the self-kill guard, the plan hold and the model-switch guard, all settings hooks in the workspace's project settings, and the review class's Bash fence, a hook in the code-review agent's frontmatter. Each runs a script from its login's own fabric checkout. In Claude Code's documented order, a `PreToolUse` hook from a project or user settings file, or from a plugin or an agent's frontmatter, runs after the last mod, and a mod that approves a call can approve one such a hook blocked. Only hooks in managed settings run before every mod, and only their block is final. This host has no managed settings at all.

So, the day the pin moves to 2.1.287 or later, any session could write and load a mod that sets every guard aside, and nothing in the fleet would show it. The pin was 2.1.285 when this was written.

The same mechanism offers what the fleet lacks. A first-loaded mod sees every tool result before Claude reads it, so it can redact the values of the login's own secrets. A secret printed by a subagent on 2026-10-04 would have reached its transcript as a name, not a value. A mod can also hold state and draw a pane, so the GZCoord inbox need not be a monitor re-armed every thirty minutes.

## 2. Decision

User-installed mods never load on a fleet host, and neither do mods Claude writes during a session. The fleet's guards move into managed settings, where they run before any mod and their block is final. The fleet's own mods load first, from a marketplace directory that only root can write. The pin does not move to 2.1.287 or later on a host until all of this is in force there.

## 3. Alternatives Considered

- **Leave mods on, as the default ships.** Rejected: a session can write and load a mod that approves past every guard the fleet's authority depends on.
- **`disableAllHooks` in managed settings.** It stops every mod, but it also stops every settings hook, managed ones included, so it removes the guards with the mods.
- **Keep the guards in project settings and only refuse users' mods.** It keeps users' mods out, but the guards stay where any later relaxation of the policy makes them overridable. They also stay in a file, and run scripts from a checkout, that the login itself can edit. Managed settings close both.
- **A mod in place of each guard.** Mods can rewrite where hooks can only refuse, but a guard should be the smallest thing that can refuse, and a crash of the mods worker unloads every non-built-in mod for the session. The guards stay settings hooks, in managed settings. Mods add to them; they do not replace them.

## 4. Rationale

Claude Code's own documentation fixes the precedence: managed `PreToolUse` hooks first and final; then mods in load order; then project, user and plugin hooks. A guard is a guard only where nothing can run ahead of it. Managed settings are also the only place the built-in guard's `allowManagedModsOnly` option and `disableSideloadFlags` are read, and the only place that makes a mod count as the organization's.

A managed hook that runs a script from a login's own checkout is no stronger than that checkout, which the login writes. The guards therefore run a root-owned copy, installed by the host's operator, as the pinned Python is (ADR-040). The fleet's mods come from a root-owned marketplace directory, loaded in place, which is what makes them count as the organization's.

## 5. Binding Rules

1. Every fleet host has `/etc/claude-code/managed-settings.json`, rendered from a template committed in agent-fabric and installed by the host's operator as root. Its `pluginConfigs` set the built-in guard's `allowManagedModsOnly` option to `true`, and it sets `disableSideloadFlags` to `true`. The guard has two names, each valid in one place: `pluginConfigs` reads its options only under `cc-plugin-sec-default@builtin`, and `prependPlugins` lists it as `sec-default@builtin`.
2. The fleet's guards are hooks in that managed settings file, not in the workspace's project settings or an agent's frontmatter: the dispatch, subagent clone, pipe-status, self-kill and job-copy guards, the plan hold and the model-switch guard, and the review fence, a managed `PreToolUse` hook that denies Bash and every writing tool to the code-review agent by the `agent_type` in its input (ADR-065 rule 1). Each is an exec-form hook (`command` an absolute path, `args` the guard's name, so no shell parses it) naming one root-owned entry, `runtime/claude-code/managed/hook_entry.py`, run by the pinned `fabric-python` in isolated mode, which accepts only the names in its own table, clears the environment to a fixed list, sets the fabric root and `PATH` itself and runs the guard with an absolute interpreter: the session's environment chooses nothing a guard runs (A 2026-10-31). The entry and every file a guard reads or runs come from a root-owned snapshot of one named commit of the fabric's main, extracted by git plumbing from the object store and never by `git archive` or a checkout, whose filters would run as root; never a script in a login's checkout. A hook that only informs the session (its start context, the tab title, a fallback note) stays in the workspace's settings.
3. The fleet's own mods live in agent-fabric and are installed by the operator into a root-owned marketplace directory, listed by relative path and loaded in place. Managed settings enable them, and `prependPlugins` lists them followed by `sec-default@builtin`: a managed `prependPlugins` replaces the default order, so a list without the built-in guard drops it.
4. The first fleet mod redacts, from every tool result before Claude reads it, the exact values of the secrets that login's `fabric-secrets sync` provides, replacing each with its name. It loads first and fails closed: a result it cannot check reaches Claude as a refusal, not unredacted.
5. Any other mod a session or an agent wants is a proposal to fabric-coordinator: reviewed with `claude plugin validate` (its `hooks:` and `calls:` named in the pull request) and the blind review, then installed under rules 3 and 6.
6. The Claude Code pin in `harness.json` moves to 2.1.287 or later only after `fabric-ctl all` reports, on every host, that rules 1 and 2 are in force. That means a session started with `--plugin-dir` on a test mod refuses it, and a guard's managed hook answers.
7. Before `disableSideloadFlags` is set on a host, a live read-back confirms that nothing the launcher or a role's profile passes is a flag it rejects (`--plugin-dir`, `--plugin-url`, `--agents`, `--mcp-config`), recorded under `docs/live-checks/`.
8. A mod or MCP server that executes code or a shell command on a session's behalf is admitted only if every such execution passes the fleet's guards as a Bash call would. The guards that match Bash do not match an MCP tool's call, and no hook sees what a server's process runs, so a server that runs code unguarded is refused, whatever it saves the session. A child process is not a sandbox unless it is shown to be one (its environment, files and network named) (A 2026-10-09). The gate is rule 1's managed settings: `allowManagedMcpServersOnly`, with `allowedMcpServers` naming each server reviewed under rule 5, its command and version pinned. Until a host has that in force, an MCP server a managed project already configures stands until its review; an unpinned version (`@latest`) does not pass it (A 2026-10-09).
9. `fabric-managed` installs rules 1 and 2 on a host, as root and only from a sha the operator names from the fabric's main, and is the only way they reach it: a guard change is in force on a host when its operator has run it there. The owner accepted that step on every guard change (A 2026-10-31). On a host where `/etc` does not survive a reboot (a Qubes AppVM), it keeps the rendered file under `/usr/local` and writes a boot hook that restores it. `fabric-managed check`, run by `fabric-ctl all status`, reports each host as in force, missing, drifted, tampered or unreadable against a fresh render of main, and until it reports in force, the workspace's own copies of the guards still run (A 2026-10-31).

## 6. Consequences

- A session can no longer extend Claude Code by writing a mod for itself. Every mod is a fabric change, reviewed like a guard.
- Installing a guard or a fleet mod needs root on each host, so it moves with the operator's distribution, not only with `fabric-ctl all upgrade fabric`. A guard change reaches a host only when its operator installs it.
- The guards become stronger than they are today, mods aside: a login can no longer weaken its own guard by editing its checkout.
- The redaction mod makes a printed secret a name in the transcript. Secrets have left the session's environment (ADR-038 rule 9) but still sit in each login's files, which a session can read.
- Two sources of truth for a guard's script exist during the move: the checkout's and the installed copy. The installed copy is authoritative once managed settings name it, and a check reports drift between the two.

## 7. Future Evolution

The GZCoord inbox as a mod with a timer and a pane, replacing the monitor a session re-arms. Panes for the fleet's state (`fabric-ctl` status, memory pressure, the open pull request's checks). An audit mod, loaded first, that records every call other mods make. Each one is a later amendment and a pull request.

## 8. Decision Status

Accepted by the owner's merge of agent-fabric #97, which carried it. Not yet in force on any host. Rules 1 and 2 are built (A 2026-10-31): the template, `fabric-managed` and its check, read back on 2.1.316 (`docs/live-checks/2026-10-31-managed-settings-2-1-316.md`, which also meets rule 7). Installing them needs root on each host and is the owner's, and the pin stays at 2.1.286 until `fabric-ctl all` reports them in force (rule 6). The redaction mod (rules 3–4) is not built.

## References

- Claude Code documentation: Mods overview (`/docs/en/plugins/mods/overview`); Manage mods for your organization (`/docs/en/plugins/mods/admin`).
- `runtime/claude-code/workspace/settings.json` (the guards as project-settings hooks today); `runtime/claude-code/harness.json` (the pin).
- ADR-005 and ADR-020 (dispatch and review guards), ADR-018 (authority), ADR-040 (the pinned interpreter, installed by the operator).

## Amendments

The body above reads current; each change's full note is in [history/ADR-043-amendments.md](history/ADR-043-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-09 | A mod or MCP server that runs code passes the fleet's guards | §5 rule 8 added: code or shell a mod or MCP server executes for a session must pass the fleet's guards as a Bash call would; a server that runs it unguarded is refused at review; a child process is not taken for a sandbox |
| 2026-10-09 | Rule 8 names its gate: the managed MCP allowlist | §5 rule 8: the gate is managed `allowManagedMcpServersOnly` + `allowedMcpServers` after a rule 5 review, version pinned; servers a managed project already configures stand until reviewed; the Bash-matched guards, not every hook, are what an MCP call escapes |
| 2026-10-31 | Rules 1–2 built: exec-form guards through one root-owned entry, a snapshot of a named main, `fabric-managed` | §5 rule 2: exec form, `hook_entry.py`, environment cleared, snapshot by git plumbing, review fence by `agent_type`, informing hooks stay; rule 9 added: operator install per guard change (owner, 2026-10-31), AppVM boot restore, the five-state check; §8 status |
