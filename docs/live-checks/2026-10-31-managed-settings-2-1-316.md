# 2026-10-31: what does Claude Code 2.1.316 do with managed settings?

**Why.** ADR-043 rule 6 holds the pin (2.1.286) until rules 1 and 2 are in force on every host, and job j509 builds them: a managed-settings template, a root installer and a check. The design rests on four claims taken from documentation, read back here on the target build before anything is built. (1) Managed settings are read from `/etc/claude-code/` and nowhere a login chooses. (2) A managed `PreToolUse` hook answers, and its deny stands. (3) `disableSideloadFlags` refuses `--plugin-dir`, and it is safe for the fleet's own launches (rule 7). (4) Nothing a login writes switches a managed hook off.

**How.** 2.1.316, the newest build that day, was installed into a scratch `HOME` with `HOME=<scratch> claude install latest`, so the account's own install and its pin stayed at 2.1.286. Each case ran `claude -p` on that binary as uid 1000, with the login's setup token and a scratch `HOME`. A case that needed `/etc/claude-code/` ran in a private mount namespace (`sudo unshare -m --propagation private`). The namespace put an overlay on `/etc` with a tmpfs upper, installed the case's managed file there, then dropped to uid 1000 with `setpriv` to run claude. No other process on the host saw the file, and nothing persisted: `ls /etc/claude-code` on the host said "No such file or directory" before and after. The owner approved running it as root this way that day. The managed probe hook was a `PreToolUse` `Bash` matcher whose command printed `permissionDecision: deny` with the reason `RBPROBE-MANAGED-HOOK-DENIED`. The prompt asked for `echo RBPROBE-BASH-RAN`, with `--allowedTools Bash`. The full managed file added `pluginConfigs."cc-plugin-sec-default@builtin".options.allowManagedModsOnly: true` and `disableSideloadFlags: true`. The test plugin was a directory with one command that answers `RBPROBE-MOD-LOADED`.

**Measured on develop-qzapp, 2026-10-31, 2.1.316:**

| case | managed file | result |
|---|---|---|
| C1 control: Bash | none | the command ran; debug log: `cc-plugin-sec-default@builtin not seated: no managed settings and not a Team or Enterprise organization` |
| N1 Bash | hook only | denied, the model quoting `RBPROBE-MANAGED-HOOK-DENIED`; `sec-default@builtin loaded (native, … tier prepend)` |
| C2 control: `--plugin-dir` | none | the plugin loaded (`RBPROBE-MOD-LOADED`) |
| N2 `--plugin-dir` | full | refused at start, exit 1: `--plugin-dir is disabled by your organization's managed settings (disableSideloadFlags)` |
| N3 Bash | full | denied by the managed hook |
| N4 `--mcp-config` | full | ran (exit 0); the binary's message for this case is "forbids --mcp-config on this machine; ignoring", so it is dropped, not refused |
| N5 `--agents` | full | refused at start, exit 1, same message as N2 |
| N6 Bash, `CLAUDE_CODE_MANAGED_SETTINGS_PATH=<empty dir>` | full | denied: the env var did not move the session off the `/etc` file |
| N7 Bash, user settings `{"disableAllHooks": true}` | full | denied: a login's own `disableAllHooks` leaves a managed hook in place |

Without root, `CLAUDE_CODE_MANAGED_SETTINGS_PATH` pointed at a scratch folder, and then at the file itself, was not read: the debug log still looked only at `/etc/claude-code/managed-settings.json` and found it missing. A login therefore cannot hand itself managed settings through the environment, nor, by N6, take away the host's.

**Rule 7, the fleet's own flags.** During the read-back the host's process table held 30 `claude` processes across its accounts, and none carried `--plugin-dir`, `--plugin-url`, `--agents` or `--mcp-config`. In the tree, those flags appear only in the launcher's option-parsing tables (`tools/fabric/launcher/base.py` `VALUE_OPTIONS`, `PATH_OPTIONS`). `memory_hint.py` passes `--strict-mcp-config` with no `--mcp-config`. The fleet's MCP servers (`fabric-memory`, `fabric-review`) are user-scope entries in each login's `.claude.json` (`install_agent_files.py`), not sideloaded. Nothing the fleet launches is refused by `disableSideloadFlags`.

**Not measured here.**
- A managed hook running a root-owned script under `/usr/local/lib/agent-fabric/hooks/`. Where the command lives does not change how a hook is run, but it is read back on the real install.
- A project-scope `disableAllHooks`; only user scope was run.
- A JavaScript mod refused by `allowManagedModsOnly` alone. `disableSideloadFlags` refused the only sideload path a session has (N2), so the mod never got as far as the guard.
- The code-review agent's Bash fence as a managed hook keyed on `agent_type`.
- Any build but 2.1.316.

**What it decides.** The plan for j509 stands on 2.1.316. The template sets both of rule 1's keys and carries the guards as managed hooks. `disableSideloadFlags` is safe to set now (rule 7 met). `fabric-ctl`'s in-force check reads `/etc/claude-code/managed-settings.json` and nothing else. Rule 6's own test is N2 (the session refuses `--plugin-dir`) and N1 or N3 (a managed hook answers). These are what the check runs on each host after the install, against the real `/etc`.
