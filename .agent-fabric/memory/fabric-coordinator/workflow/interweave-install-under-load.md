---
role: "fabric-coordinator"
class: workflow
topic: "interweave-install-under-load"
description: "fabric-ctl all interweave-install under host load fails some accounts with \"carrier does not answer\"; retry one at a time, and stop/install/start an account whose carrier does not answer even on the old programs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a2a7e5cc8da869ad
---

## fabric-ctl all interweave-install under host load fails some accounts with "carrier does not answer"; retry one at a time, and stop/install/start an account whose carrier does not answer even on the old programs

2026-10-28, InterWeave 0.1.0 → 0.2.0 on 28 accounts (j401): `fabric-ctl all
interweave-install` while a full tests/run.sh ran (load ~20 on 10 vCPU) failed 6
accounts with "the InterWeave channel did not come back on the new programs
(gzcoord-carrier status exited 3)"; the installer restored 0.1.0 on each.
Retried one at a time afterwards: 5 installed with "units: passed". The sixth
(flutter-dev-02) still failed, and its carrier did not answer on the old
programs either. `interweave-stop`, then `interweave-install` ("not run: no unit
was running"), then `interweave-start` brought it up on 0.2.0, channel ok.

**How to apply:** run a fleet install with no suite or build running on the
host; read `fabric-ctl all interweave` after it; retry the failed accounts one
at a time before calling it a defect of the release; for one whose carrier fails
on both versions, stop, install, start. After the fleet moves to one version the
parity window restarts ([[interweave-pin-bump-procedure]],
[[interweave-install-control-plane-check]]).

*References: interweave-install-control-plane-check, interweave-pin-bump-procedure*

*Anchors: `tools/fabric/control/carrier_install.py::PIN_REL`*

*Observed 2026-10-28 (fabric-coordinator)*
