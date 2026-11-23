---
role: "p2p-network-dev"
class: domain
topic: "systemd-result-resets-on-restart"
description: "systemd's Result= of a service is reset when an auto-restarted run starts, so it cannot tell a SIGHUP success from a SIGKILL failure; the journal's per-run 'Failed with result' line can"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - cc02e3ffeb222f0b
---

## systemd's Result= of a service is reset when an auto-restarted run starts, so it cannot tell a SIGHUP success from a SIGKILL failure; the journal's per-run 'Failed with result' line can

Measured 2026-10-20 (systemd 258, user manager, j94 `tests/desktop-e2e/tests/user_units.rs`): after an
auto-restart, `systemctl show -p Result` reads `success` whether the previous run exited with a
SuccessExitStatus= code or was SIGKILLed — the SIGKILL control asserting `signal` failed. So `Result=` read
after a restart proves nothing either way. The oracle that works is the unit's journal (`journalctl --user
-o cat -u <unit>`): each failed run leaves `<unit>: Failed with result '<kind>'.`, each scheduled restart
`<unit>: Scheduled restart job, restart counter is at N.`; a SuccessExitStatus= exit leaves neither a
`Main process exited` nor a `Failed` line. Poll for the Nth "restart counter" line, then count "Failed with
result" lines. `NRestarts=` does count restarts reliably.

**Why:** a positive control beside the negative assertion is what caught the vacuous oracle.
**How to apply:** for any "logged as a success / failure" claim about a restarted unit, read the journal,
and keep a control run that must produce the failure line.

*Observed 2026-10-20 (p2p-network-dev)*
