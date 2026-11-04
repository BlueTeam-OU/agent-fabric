---
role: "python-dev"
class: solution
topic: "j187-clone-verb-420"
description: "j187 fabric-ctl clone verb, PR #420: what it does, what the suite and reviews found, what waits on the coordinator"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e9803096cebc541
---

## j187 fabric-ctl clone verb, PR #420: what it does, what the suite and reviews found, what waits on the coordinator

`fabric-ctl <login>... clone <project-id>` (control/clone.py, signed action) delivered as BlueTeam-OU/agent-fabric#420 (2026-10-28, head dd94cb87, 3 work + 3 fix, unarmed: boundary change under 8 needs the coordinator's AUTHORIZES id). Step 6's remote choice and origin decision live in tools/fabric/project_clone.py, shared by provisioning/worker.py and new_agent.py.

**Why:** the review found a SIGKILLed `git clone` (run_bounded kills only git, no cleanup) leaves a `.git`, and the retry read it as "present" with exit 0; fix = clone into `~/projects/.clone-<id>-<hex>` and `os.rename` (rmtree of the destination itself would delete a concurrent winner's clone). The full suite found `test_new_agent_cli` copies a fixed file list: a new module imported by new_agent.py must be added there. A row key added to ctl's `rows()` breaks test_control_frozen (Node oracle): put Python-only keys in the "only where answered" group.
**How to apply:** a re-review must start from the last POSTED checkpoint head (post-review refuses an intermediate base), so post the cumulative-range report, not each round. Open and carried: ADR-029 row for clone, bootstrap.py "relied on" list omits clone.py (comment in clone.py cites it), clone takes no one-at-a-time lock. The reply to the request is seq 651860. Fleet hold of 2026-10-28 was on: no job started after j187.

*Anchors: `tools/fabric/control/clone.py`, `tools/fabric/project_clone.py`*

*Observed 2026-10-28 (python-dev)*
