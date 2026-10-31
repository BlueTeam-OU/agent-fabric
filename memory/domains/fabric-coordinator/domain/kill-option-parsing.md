---
role: "fabric-coordinator"
class: domain
topic: "kill-option-parsing"
description: "How bash's kill builtin and util-linux kill read options: which later words can still change the signal after kill -0, and why -- makes any operand safe"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 26fa1912cfc062bc
---

## How bash's kill builtin and util-linux kill read options: which later words can still change the signal after kill -0, and why -- makes any operand safe

Read from the sources on 2026-10-18 (bash 5.3 `builtins/kill.def`, util-linux 2.41 `misc-utils/kill.c`), not from
memory: an earlier guess ("the last -N wins") was wrong.

- **A second `-N` is a process group, not a signal.** bash takes only the first bare `-SIG`/`-N` as the signal
  (`saw_signal == 0`); util-linux breaks out of option parsing at an unknown dash word once a signal is set.
- **But named options still set a signal anywhere before the pids**: bash `-s SIG`, `-sSIG`, `-n NUM`, `-nNUM`;
  util-linux `-s`, `--signal`, `--timeout N SIG`. So `kill -0 $a $b` with `a=-sKILL b=-1` is `kill -sKILL -1`.
- **`--` ends options in both**: after `kill -0 --`, every word is a pid or job given signal 0, which signals
  nothing, whatever a variable holds.
- `kill -0 "$one"` is safe: a value that is an option leaves no pid (usage error).
- **Unquoted `kill -0 $x` is NOT safe**, and calling it "a residual only a crafted value reaches" was wrong: the blind
  review of #297 (F1, P1) passed `x='-s KILL -1'; kill -0 $x`, `IFS=,` splitting, and `xargs kill -0 $x` (xargs
  appends operands after it) straight through to `kill -sKILL -1`. Round 2 then passed it again past a text-based
  "quoted or `=$!`" test (a quoted sibling kill, an indirect `declare`): a guard that reads quote-stripped words
  cannot tell `"$x"` from `$x`. The only exemption that holds is `kill -0 -- <anything>` (2915f411).
- `kill -- -0 x` is group 0 with SIGTERM, not a probe.

Applied in `runtime/claude-code/hooks/self-kill-guard.py` `_zero_probe` (d87ae641, corrected by aa9a8b52 after review F1; branch
develop-qzapp/user/feat/locale-suffix-retire).

*Observed 2026-10-18 (fabric-coordinator)*
