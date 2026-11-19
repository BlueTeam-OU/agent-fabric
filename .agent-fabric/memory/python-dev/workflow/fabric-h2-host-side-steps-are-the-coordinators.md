---
role: "python-dev"
class: workflow
topic: "fabric-h2-host-side-steps-are-the-coordinators"
description: "a python-dev account has no ssh path to fabric-h2; the op key is the operator's, so a two-host read-back is driven from develop-qzapp with the coordinator running the host side"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f83eedf525143d5d
---

## a python-dev account has no ssh path to fabric-h2; the op key is the operator's, so a two-host read-back is driven from develop-qzapp with the coordinator running the host side

From develop-qzapp, `fabric-host fabric-h2 check` and `ssh op@a private-network address` fail for a
python-dev login with "Host key verification failed" (known_hosts holds only github; the op key
on the host is the coordinator's). j127 (j880, W10's two-host read-back, 2026-11-14/15).

**Why:** the coordinator answered that placing a login on a host is provisioning and the op key is
the operator's; it creates the scratch login, its InterWeave profile and roster row, then names it.

**How to apply:** for any fabric-h2 read-back, block on the scratch-login job
(`fabric-jobs block <id> --on job:<login>/j<n>`; free text is refused), drive both directions from
develop-qzapp, ask the coordinator to run host-side commands at my word, and write the record.

*Observed 2026-11-15 (python-dev)*
