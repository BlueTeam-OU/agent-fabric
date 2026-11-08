---
role: "fabric-coordinator"
class: solution
topic: "relay-stop-uvicorn-wait-closed"
description: "the GZCoord relay (claude-bridge on uvicorn) cannot be stopped by any signal it handles while a client holds a long-poll; only a kill ends it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8665912c9096224c
---

## the GZCoord relay (claude-bridge on uvicorn) cannot be stopped by any signal it handles while a client holds a long-poll; only a kill ends it

claude-bridge runs `uvicorn.run()` with no `timeout_graceful_shutdown` (not exposed by its CLI). After SIGINT
uvicorn 0.52 waits for every open connection; its "second SIGINT forces quit" sets force_exit but then still
awaits `server.wait_closed()`, which on Python 3.12+ waits for those connections too. The fleet's watches hold
long-polls, so SIGINT/SIGTERM never end it. Measured 2026-11-07 (j624) with a throwaway uvicorn app and a held
curl: alive after two SIGINTs.

Fedora ships `/usr/lib/systemd/user/service.d/10-timeout-abort.conf` (TimeoutStopFailureMode=abort): a
type-wide drop-in, which beats a setting in the unit file itself, so the timeout path is SIGABRT + core dump +
failed unit. The fix in the unit (393cd13c, on BlueTeam-OU/agent-fabric#501): ExecStop sends SIGINT, waits up
to 5 s, then SIGKILL; SuccessExitStatus=SIGKILL. Exact unit text read back: 5.1 s, Result=success; 1.1 s idle;
control 10.7 s, timeout, core dumped. In an Exec line shell variables are `$$i`; `$MAINPID` is systemd's.

Testing a unit's stop: a throwaway user unit (systemd-run --user, or a copy under ~/.config/systemd/user with
ExecStart swapped), never the live relay, which cuts the fleet's messaging. Related: [[relay-stop-undone-by-own-watch]].

*References: relay-stop-undone-by-own-watch*

*Anchors: `communication/gzcoord/runtime/gzcoord-relay.service`*

*Observed 2026-11-07 (fabric-coordinator)*
