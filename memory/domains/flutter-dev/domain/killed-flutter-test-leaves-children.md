---
role: "flutter-dev"
class: domain
topic: "killed-flutter-test-leaves-children"
description: A flutter test run killed by the harness (timeout, OOM) leaves its dartvm and frontend_server children alive for hours, and they are what starve the next run.
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - d3197c5891210dd2
---

## A flutter test run killed by the harness (timeout, OOM) leaves its dartvm and frontend_server children alive for hours, and they are what starve the next run.

**When a `flutter test` run is killed — a harness timeout, an OOM stop —
its CHILDREN survive.** Found 2026-09-17: a bare `flutter test` on
passenger_flutter still running after **7h48m**, with its
`frontend_server_aot` beside it, together holding ~978 MB RSS on a host
with ~16 GB available. They were mine, from a run killed much earlier
in the session.

**They are what starved the later runs.** Two consecutive full-suite
attempts were OOM-killed while those orphans sat idle; after killing
them the memory came straight back. I had been blaming other accounts'
toolchains, which were present but not the cause I could act on.

**So: after any killed or timed-out flutter run, check for orphans
before blaming the host.**

```sh
ps -o pid,user,etime,rss,stat -p $(pgrep -f '[f]lutter_tools' | tr '\n' ',')
```

An `ELAPSED` far past a normal run (passenger ~2.5 min, driver ~3 min)
is the tell. **Kill by exact PID** — never `pkill -f`, which has killed
this session's own shell twice, see [[pkill-f-matches-your-own-shell]].
Kill the compiler child and the tools parent together.

CLAUDE.md already says it — long-lived local processes are owned by the
session that started them, "a killed run still owes its cleanup" — and
this is the shape that rule is about. The harness reporting "stopped
because the system is running low on memory" does NOT mean it reaped
anything.

Related: [[pkill-f-matches-your-own-shell]].

*References: pkill-f-matches-your-own-shell*

*Observed 2026-09-17 (flutter-dev)*
