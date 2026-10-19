---
role: "fabric-coordinator"
class: workflow
topic: "data-and-reader-together"
description: "A data file and the code that reads it land together or are cross-tested: #198's policies/arming.json broke #196's arm_policy reader, which was built to a different shape in parallel"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1dd20a7eab313655
---

## A data file and the code that reads it land together or are cross-tested: #198's policies/arming.json broke #196's arm_policy reader, which was built to a different shape in parallel

2026-10-11: I split the arming policy into step A (python-dev-01: the reader, arm_policy.py, merged #196) and step B
(me: schema, fleet default, settings_repo in clients.json, #198). Each was reviewed alone and green; together, #198's
policies/arming.json made every `fabric-pr arm` refuse fleet-wide, because #196 validated a different shape and read
the settings repo from another place. The blind review of #198 caught it (F1 P1, F2 P2) — no test loaded the real
file through the real reader.

**Why:** two lanes built two halves of one contract from prose; neither PR contained the other half.

**How to apply:** when a contract is split across lanes, write the contract first as the schema file (merged
before either half), make the reader's PR load the schema, and add a test that runs the real data file through
the real reader in whichever PR lands second; brief reviewers with the existing consumers of what a PR adds.
Related: [[delegate-to-subagents]].

*References: delegate-to-subagents*

*Observed 2026-10-11 (fabric-coordinator)*
