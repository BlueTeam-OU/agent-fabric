---
role: "fabric-coordinator"
class: workflow
topic: "artifact-handoff-by-reply"
description: Never hand a file between accounts through a shared /var/tmp or scratch directory; ask for it verbatim in a REPLY between BEGIN and END markers with its sha256, and write it myself
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 33313d9a7d61350e
---

## Never hand a file between accounts through a shared /var/tmp or scratch directory; ask for it verbatim in a REPLY between BEGIN and END markers with its sha256, and write it myself

Twice a holder's permission check refused copying an artifact into a shared directory for me. A verbatim REPLY with BEGIN/END markers and a sha256 worked both times.

**Why:** cross-account file paths hit permission checks and home modes; the relay carries text both sides can verify.
**How to apply:** for a file under about 48 KiB, ask for it in a REPLY with markers and a sha256, write it, and compare the digest. Larger files travel by git or the control plane. Related: [[cross-host-share-via-control-plane]], [[addenda-reissue-parent-builds]].

*References: addenda-reissue-parent-builds, cross-host-share-via-control-plane*

*Observed 2026-10-22 (fabric-coordinator)*
