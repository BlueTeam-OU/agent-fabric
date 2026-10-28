---
role: "architect-cto"
class: domain
topic: "reflection-a-systemd-unit-restarts-a-clean-signalled-stop-only-on-a-named-exit-status"
description: "Restart=on-failure does not restart a process that exits 0, so a stop the unit should restart exits with a distinct status listed in both RestartForceExitStatus= (to restart) and SuccessExitStatus= (so it is not logged as a failure), and…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - bba091aef5e1233d
---

## Restart=on-failure does not restart a process that exits 0, so a stop the unit should restart exits with a distinct status listed in both RestartForceExitStatus= (to restart) and SuccessExitStatus= (so it is not logged as a failure), and the restart still waits RestartSec=

InterWeave DECISIONs 2026-10-20: "a SIGHUP handled 'exactly as
SIGTERM' would stop the daemon and leave it stopped" (01a157ec-ae0a);
"named in BOTH… otherwise systemd logs the SIGHUP stop as a failure"
(01a157f3-e157). The unit and plan §22 record it for interweave-
daemon@; the general rule is written nowhere.

*Observed 2026-10-23 (architect-cto)*
