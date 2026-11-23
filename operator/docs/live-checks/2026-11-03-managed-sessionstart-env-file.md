# 2026-11-03: does a managed SessionStart hook reach the session's shell?

**Why.** ADR-038 rule 9's shell seal moves into the managed settings (job j510, ADR-043 rule 2). The seal works only if a managed `SessionStart` hook is given `CLAUDE_ENV_FILE` and the harness sources what it writes into the session's Bash calls. The 2026-10-31 read-back (`2026-10-31-managed-settings-2-1-316.md`) covered `PreToolUse` hooks only. So until this check, the ADR-043 amendment of 2026-11-03 called the managed copy unmeasured.

**How.** The method was the 2026-10-31 one, which the owner approved again for this check on 2026-11-03. Each case ran in a private mount namespace (`sudo unshare -m --propagation private`). An overlay on `/etc` with a tmpfs upper held the case's `/etc/claude-code/managed-settings.json`, so the operator's installed file on the host was neither read nor changed. Claude then ran as uid 1000 through `setpriv`, with a scratch `HOME`, the login's setup token and `RBPROBE_SECRET=planted` in its environment. The prompt was `claude -p --allowedTools Bash`, asking Bash for `echo "RBPROBE_SECRET=${RBPROBE_SECRET:-unset}"`. The probe hook was `/usr/bin/python3 -I -S probe.py <log>`. It logged whether `CLAUDE_ENV_FILE` was set, then appended `unset RBPROBE_SECRET` to that file. Exec form means `command` is the interpreter and `args` is the rest. Shell form means the same words as one `command` string. Builds tested: 2.1.316, installed into a scratch `HOME`, and 2.1.286, the fleet's pin.

**Measured on develop-qzapp, 2026-11-03:**

| case | managed file | login's settings | 2.1.316 | 2.1.286 |
|---|---|---|---|---|
| control | `{}` | none | `planted` | not run |
| exec form | the probe | none | `unset`; probe ran, `CLAUDE_ENV_FILE=…/session-env/<sid>/sessionstart-hook-0.sh` | same |
| shell form | the probe | none | `unset`, same file name | same |
| login switches hooks off | the probe, exec form | `{"disableAllHooks": true}` | `unset`; probe ran once | same |
| control for the row above | `{}` | the probe as its own hook, plus `disableAllHooks` | `planted`; probe never ran | same |
| control for the row above | `{}` | the probe as its own hook | `unset`; probe ran once | same |

The host's `/etc/claude-code/managed-settings.json` was the operator's install of 2026-11-02 (main `1b90ade8`, no `session-seal`), the same before and after. The namespace's empty mount points under `/run` were removed afterwards.

**What it decides.**
- A managed `SessionStart` hook is given its own env file (`sessionstart-hook-N.sh`), and the harness sources it into every Bash call. This holds in exec form and shell form, on 2.1.316 and on the pinned 2.1.286. So the managed seal (`hook_entry.py session-seal`) protects a session wherever the operator has installed a file that names it.
- A login's `disableAllHooks` stops its own hooks but not a managed one. The managed copy is the one a login cannot drop, as ADR-043 rule 2 intends.
- The workspace copy (from `session-start.py`) still runs beside it. Each hook writes its own file, and an unset run twice does nothing. On a host whose installed file predates `session-seal`, which includes develop-qzapp today, the workspace copy is the only seal until the operator reinstalls.

**Not measured.**
- The real `hook_entry.py` from an installed snapshot. `tests/test_session_seal.py` runs that path on a scratch snapshot. Here a probe stood in for it.
- Resume and compaction. Each case was a new `-p` session.
- Builds other than 2.1.286 and 2.1.316.
