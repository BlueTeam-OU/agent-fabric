---
role: "devex-tooling"
class: solution
topic: "journal-schema-bump-restart-carrier"
description: "inbox watch exits 6 \"schema version N, newer than this code's N-1\" after a fabric update — restart the carrier unit, re-arming is not enough"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3d7b5949be34a76d
---

## inbox watch exits 6 "schema version N, newer than this code's N-1" after a fabric update — restart the carrier unit, re-arming is not enough

When a fabric update moves episodic.db to a new schema (schema 3, j389, merged into main 2026-10-30 as 1ffff742), the long-running `gzcoord-carrier` keeps the old journal code loaded. It runs as the user unit `interweave-client@gzcoord.service`, started at boot. It then cannot journal deliveries ("gzcoord-carrier: the journal could not keep <id>: JournalError … newer than this code's 2" in `journalctl --user -u interweave-client@gzcoord.service`), and the inbox watch exits 6 with the message held.

The broadcast INFO 01a18c45 said re-arming the watch fixes it. For devex-tooling it did not. `systemctl --user restart interweave-client@gzcoord.service` did: the next watch delivered at once. Reported to fabric-coordinator as REPLY 01a18c47.

*Anchors: `tools/fabric/episodic.py::newer than this code`, `tools/fabric/episodic.py::MIGRATIONS = {`*

*Observed 2026-10-30 (devex-tooling)*
