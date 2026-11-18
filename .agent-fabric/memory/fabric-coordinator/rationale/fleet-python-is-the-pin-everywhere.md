---
role: "fabric-coordinator"
class: rationale
topic: "fleet-python-is-the-pin-everywhere"
description: "Owner 2026-11-11 (j762): every host runs the fleet's pinned Python; a host's own python3 only bootstraps python_pin.py, so AlmaLinux's 3.12 is no blocker"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7728bafb6612d05f
---

## Owner 2026-11-11 (j762): every host runs the fleet's pinned Python; a host's own python3 only bootstraps python_pin.py, so AlmaLinux's 3.12 is no blocker

The owner said on 2026-11-11, answering j762 (AlmaLinux 10's python3 is 3.12, below ADR-040 rule 1's 3.13 floor): "the fleet should work on the same python level on every host, so … each agent should download the fleet python version the fleet use".

What follows from it:
- Every host gets `runtime/python.json`'s pin through `tools/fabric/python_pin.py install`. It is one install per host, `/usr/local/bin/fabric-python`, shared by every account there. So every agent runs the same version on every host.
- The host's own `/usr/bin/python3` only runs `python_pin.py` itself. That file has to stay valid on the oldest system python3 of a supported platform, which is now EL10's 3.12. It compiled on fabric-h2's 3.12.13 on 2026-11-11.
- `worker.prepare`'s check of the system python3 against 3.13 (tools/fabric/provisioning/worker.py, `host_python_ok`) becomes a check that `fabric-python` is the pinned build. That code is python-dev's.
- Never repoint `/usr/bin/python3` on EL: on fabric-h2, 25 installed packages require the OS's 3.12.

**Why:** a single interpreter everywhere means a script behaves the same on every host. The OS's python is the distribution's, not the fleet's.
**How to apply:** amend ADR-040 rule 1 accordingly, on the j706 branch, then REQUEST python-dev-02 (j135's holder) to change worker.prepare. Related: [[h2-owner-answers-2026-11-11]].

*References: h2-owner-answers-2026-11-11*

*Observed 2026-11-11 (fabric-coordinator)*
