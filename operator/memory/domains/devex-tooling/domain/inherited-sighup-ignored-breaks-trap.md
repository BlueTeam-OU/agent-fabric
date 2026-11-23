---
role: "devex-tooling"
class: domain
topic: "inherited-sighup-ignored-breaks-trap"
description: "A signal-case self-test fails only in some local runs — the run inherited SIGHUP ignored; non-interactive bash cannot trap it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 6898ac065b0067a4
---

## A signal-case self-test fails only in some local runs — the run inherited SIGHUP ignored; non-interactive bash cannot trap it

A non-interactive bash cannot trap or reset a signal that was ignored at its entry. A test that sends that signal to a bash wrapper then sees nothing happen.

j327 (2026-11-12): rust-services-dev-01 reported (01a1cd1e) that InterWeave `tools/ci/test_with_display.sh` failed its HUP case inside a local `cargo xtask ci` ("got 0 after 31s", "Xvfb was not terminated after HUP") but passed alone and in CI.
- Reproduced exactly by starting the suite through `python3 -c 'signal.signal(SIGHUP, SIG_IGN); os.execvp(...)'`; TERM and INT still passed.
- CPU load alone (20 busy loops) did not reproduce it.
- xtask spawns its tasks plainly, so the launcher of that run handed the ignore down (nohup or the like).
- A Claude Code background shell here ignores only SIGPIPE (SigIgn 0x1000), so the harness is not the cause.

The fix: the test's exec shim resets HUP and TERM to SIG_DFL, as it already did for INT. & jobs start INT-ignored; see [[bash-signal-cleanup-traps]].

Second trap, found by the review of InterWeave PR 632 (F1): a `python3 -c '...os.execvp(...)'` launcher itself leaves SIGPIPE and SIGXFSZ ignored. Python ignores both at its start, and os.execvp, unlike Popen's restore_signals, keeps the ignore. Reset all five signals (HUP INT PIPE TERM XFSZ) in any exec shim. The suites now fail at start if any of those is still ignored: check SigIgn against the mask 0x1005003, where the bit for signal n is n-1. Bash marks QUIT ignored for itself, so leave QUIT out of the mask.

**How to apply:** if a signal test fails in only some environments, read `grep SigIgn /proc/<pid>/status` of the run first. Reproduce by exec'ing the run with that signal set to SIG_IGN.

*References: bash-signal-cleanup-traps*

*Observed 2026-11-12 (devex-tooling)*
