---
role: "fabric-coordinator"
class: threads
topic: "dual-run-window-2026-10-28"
description: "ADR-064 dual-run parity window, restated 2026-10-30T05:00Z..2026-10-31T05:00Z (the 28→29 one had no drill) on InterWeave 0.2.0; what the report still needs (drill, TO-ROLE, evidence, parity)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 36d6b7f200a1c755
---

## ADR-064 dual-run parity window, restated 2026-10-30T05:00Z..2026-10-31T05:00Z (the 28→29 one had no drill) on InterWeave 0.2.0; what the report still needs (drill, TO-ROLE, evidence, parity)

j401, 2026-10-28: rule 13 green on 0.2.0 (python-dev-02 j97, record on #417's
branch), all 30 accounts on 0.2.0 / pinned / channel ok from ~11:47Z. I stated
the parity window as 2026-10-28T12:00Z..2026-10-29T12:00Z (rule 11 names no
length: "a stated window"). Still owed inside it: the rollback drill (carrier
off mid-window on some accounts, nothing lost, ~00:00Z on the 29th) and at least
one TO-ROLE message (sent 12:2xZ: INFO 01a18271 TO-ROLE
architect-cto stating the window, so that need is met). After it: `fabric-ctl all interweave-evidence --since ...
--until ... --out <dir>`, `gzcoord-carrier parity --collected`, the report in
docs/live-checks, then the owner's word as an ADR-033 amendment.

**How to apply:** a session resuming j401 reads the clock first; before the
drill time there is nothing to run. A pin move restarts the window
([[interweave-pin-bump-procedure]], [[interweave-install-under-load]]).

**2026-10-30: window restated.** The 28→29 window passed with no drill and almost no traffic (fleet hold from 14:18Z on the 28th, then the claude-pzhuy account at 100% weekly; my journal stops 2026-10-28T15:04Z). New window 2026-10-30T05:00Z..2026-10-31T05:00Z, all 30 accounts on 0.2.0 / pinned / both units / channel ok (fabric-ctl all interweave, 04:40Z). Drill ~17:00Z on the 30th: interweave-stop on a few accounts, interweave-start after, nothing lost. A TO-ROLE INFO stating the window goes after 05:00Z, so it falls inside.

**2026-10-30 11:30Z: window restated again, drill done.** #425 (d941d5b0, journal schema 3) reached every account 10:04Z; the boot-started carriers kept schema-2 code and journaled nothing 10:04Z–11:27Z (devex-tooling found it). Owner chose a fleet stop/start: interweave-stop 11:27:33Z, start refused (ip_local_reserved_ports empty after the 05:08Z reboot), owner ran the persisting fix, start 11:29:18Z, `fabric-ctl all interweave` 30/30 ok. That outage is the drill (carriers off mid-window). New window 2026-10-30T11:30Z..2026-10-31T11:30Z; evidence from 11:30Z.

*References: interweave-install-under-load, interweave-pin-bump-procedure*

*Observed 2026-10-28 (fabric-coordinator)*
