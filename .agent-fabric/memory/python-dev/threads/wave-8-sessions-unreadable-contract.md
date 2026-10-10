---
role: "python-dev"
class: threads
topic: "wave-8-sessions-unreadable-contract"
description: "Wave 8 sessions/ctl port must BUILD j5 (unreadable session state) in Python — not in Node; contract + 9 mutations from python-dev-02"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 36cc6294a48f3e73
---

## Wave 8 sessions/ctl port must BUILD j5 (unreadable session state) in Python — not in Node; contract + 9 mutations from python-dev-02

2026-10-09: the owner moved python-dev-02's j5 out of Node (#127 merged without it, 6e8c1702 unpushed):
it exists only as new behaviour in my Python sessions.mjs/ctl.mjs port (job j67, Wave 8).
Sources: fabric-coordinator INFO 01a11e4e-46ab-7fbb-821e-28819b57db1f; python-dev-02 INFO
01a11e4c-2569-726d-89e2-7d5e93539fe8 (items 1-4) and correction 01a11e4e-f664-7518-8f54-cedc4602d482 (cases).

Contract:
1. readSessions: absent file = [] (none); present but unreadable/unparseable/not {"sessions": {...}} = unknown (null). Same rule as resume.py live_sessions.
2. Watcher posts sessions: "unreadable" (the string, so a list-only reader drops the record). Logs once on going unreadable, once on recovery.
3. ctl stateRecordOf accepts "unreadable"; stateRow → state unknown, why "the account cannot read its session state", sessions [], since null.
4. Under state unknown, sessions is [] — `state` is authoritative; a reader counting sessions[] sees 0. Keep it.

Cases: absent → []; '{broken' → unknown; '[]','null','7','{}','{"sessions": []}','{"sessions": null}','{"sessions": "x"}' → unknown;
'{"sessions": {}}' → []; a directory at the path → unknown. Watcher: broken → post "unreadable"; tick 2 s later posts nothing;
heartbeat re-posts "unreadable"; file becomes {"sessions": {}} → post []; log holds exactly two lines
"<file> cannot be read; its sessions said as unreadable" and "<file> is readable again".
Validator: "unreadable" accepted; "none", {} and null rejected.

Mutations to kill: M1 read/parse error → []; M2 absent → unknown; M3 shape check removed; M4 watcher posts [] for unknown;
M5 unreadable line logged every tick; M6 recovery line removed; M7 row reads none for "unreadable"; M8 validator drops
"unreadable"; M9 validator accepts any string.

*Observed 2026-10-09 (python-dev)*
