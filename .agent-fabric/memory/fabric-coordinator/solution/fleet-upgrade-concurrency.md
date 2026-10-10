---
role: "fabric-coordinator"
class: solution
topic: "fleet-upgrade-concurrency"
description: "fabric-ctl all upgrade claude serializes installs per host under the fabric-lease and exits 1 on any failed row"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 6c77578f79fd718b
  - 743c634630668065
  - 97d8b90083da6f7f
---

## fabric-ctl all upgrade claude serializes installs per host under the fabric-lease and exits 1 on any failed row

`fabric-ctl all upgrade claude` is the normal path for a fleet upgrade. Run without that care (2026-09-25, 13 accounts of one host at once), 9 installs failed; the same installs one at a time all succeeded.

Now built in: each install runs under the host lease (`fabric-lease`, ADR-010), so one account installs at a time per host; a failed install reports the error's LAST non-empty line, not execFile's first; and `fabric-ctl ... upgrade` exits 1 when any row failed (tools/fabric/control/upgrade.py with `LEASE_HELD = 75`; tools/fabric/control/ctl.py; the Node twins in runtime/control/).

**How to apply:** read the exit status and every row after an upgrade, never only the summary; a lease-held row means another install holds the host, so retry it.

*Observed 2026-10-10 (fabric-coordinator)*
