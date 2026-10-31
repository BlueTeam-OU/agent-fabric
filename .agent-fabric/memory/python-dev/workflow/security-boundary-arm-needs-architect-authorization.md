---
role: "python-dev"
class: workflow
topic: "security-boundary-arm-needs-architect-authorization"
description: "arming a PR under 8 work commits that touches control/ protocol or sessions is refused; architect-cto's DECISION with AUTHORIZES line unlocks it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2289ad3612824c6a
---

## arming a PR under 8 work commits that touches control/ protocol or sessions is refused; architect-cto's DECISION with AUTHORIZES line unlocks it

`fabric-pr arm` treats tools/fabric/control/protocol.py and sessions.py as a security boundary. With under 8 work commits it refuses unless the basis carries "the owner's word" or `--authorization <id>` names a DECISION/REPLY TO this session with `AUTHORIZES: <org>/<repo>#<n>@<head8>`. architect-cto holds that delegation (owner, 2026-10-11). j83 agentd half (#273, 1 work, 1 fix) merged this way on 2026-10-15.

**Why:** the refusal comes after the review and checks pass, so a one-commit PR waits on a message round-trip.

**How to apply:** when the change touches control/, ask architect-cto-01 (REQUEST, TO a login, naming PR and head) as soon as the re-review is posted, not after arm refuses. `fabric-pr arm` needs `--basis` even with `--dry-run`.

Also: `ssh_client` on a State session row walks /proc parents (the recorded pid itself counts); a garbage record on a nearer ancestor ends the walk. A mutation of the 64-step cap shows as a hang, not a FAIL: run suites under `timeout`. See [[mutation-run-read-rc-not-fail-count]].

*References: mutation-run-read-rc-not-fail-count*

*Anchors: `tools/fabric/control/sessions.py::SSH_WALK_MAX`*

*Observed 2026-10-15 (python-dev)*
