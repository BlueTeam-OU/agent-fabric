---
role: "p2p-network-dev"
class: domain
topic: "sighup-under-systemd-needs-its-own-exit-status"
description: "An unhandled SIGHUP kills a daemon at once (no grace, no orderly stop); handling it 'as SIGTERM' under a Restart=on-failure unit leaves the daemon STOPPED, because a clean exit 0 is not restarted. A signal meant as 'restart' needs its own…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b25bb71b0f8e61d
---

## An unhandled SIGHUP kills a daemon at once (no grace, no orderly stop); handling it 'as SIGTERM' under a Restart=on-failure unit leaves the daemon STOPPED, because a clean exit 0 is not restarted. A signal meant as 'restart' needs its own exit status, named in both SuccessExitStatus= and RestartForceExitStatus=, read by the test from the unit file

InterWeave's transport-daemon handled SIGINT and SIGTERM only. SIGHUP's
default action ended the process at once, skipping SHUTDOWN_GRACE and the
server's stop. A shell or unit manager that sends HUP on hangup did that
to a daemon holding connections. The ruling (Stage 19, #317, plan §22)
was "no reload; SIGHUP = an orderly stop and a restart". It took three
rounds to say correctly:

1. "Handle it exactly as SIGTERM; the unit restarts it" was false. The
   shipped unit had `Restart=on-failure`, and a clean stop exits 0, so the
   daemon would stay down and take its client unit with it.
2. The stop has to exit with a DISTINCT status (not 0, and not one that
   `RestartPreventExitStatus=` names), listed in `RestartForceExitStatus=`
   so the unit restarts.
3. The same status also has to go in `SuccessExitStatus=`, or systemd
   logs every HUP as a failure. The restart still waits `RestartSec=`, so
   a HUP is not the immediate stop/start of `systemctl restart`. The
   status joins the program's exit-code contract, and the test reads the
   number from the unit file, not from a constant, so daemon and unit
   cannot drift.

Hosted GitHub runners already run a lingering user manager with a user
journal (ubuntu-24.04, systemd 255): `systemctl --user` works once
XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS are exported into the step.
So these unit cases can run in CI.

**How to apply:** for any daemon shipped with a unit, list every signal
the platform may send (HUP, TERM, INT, PIPE) and what the default does,
then derive the exit status from the unit's Restart= policy. Test the
signal → stop sequence → exit status → unit restart chain end to end.
Related: [[systemd-result-resets-on-restart]].

*References: systemd-result-resets-on-restart*

*Observed 2026-10-25 (p2p-network-dev)*
