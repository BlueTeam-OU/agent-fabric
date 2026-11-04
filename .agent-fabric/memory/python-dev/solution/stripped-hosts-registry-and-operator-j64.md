---
role: "python-dev"
class: solution
topic: "stripped-hosts-registry-and-operator-j64"
description: "j64 — two stripped-red causes: queue.py reads the hosts registry before the relay; review_brief resolves project via operator registry"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 34b4eed19ecd7bcd
---

## j64 — two stripped-red causes: queue.py reads the hosts registry before the relay; review_brief resolves project via operator registry

j64 (branch develop-qzapp/python-dev-03/feat/j64-stripped-nightly-red-tests-test-session, 05ba94cc). tests/test_session_start.py: `fabric-jobs list` asks tools/fabric/control/queue.py, which reads the hosts registry (runtime/hosts/registry.json) BEFORE calling the relay; stripped copy has none, so the relay is never hit and the positive control fails. Fix: AGENT_FABRIC_HOSTS_REGISTRY -> instance_fixtures.HOSTS_REGISTRY. tests/test_subagent_ledger.py: review_brief.dispatch_header resolves project/repository via workingcopy.resolve in-process (operator registry), so null fields on a stripped copy. Fix: fixture registry + os.environ AGENT_FABRIC_OPERATOR.

**Why:** the failure message names the symptom (relay not hit, a null field), never the missing file; find it by reading what the tool opens first.
**How to apply:** for a stripped-red test, trace the tool's first file reads (roots.py helpers) and give each a fixture via its env override. See [[stripped-operator-fixture-j63]].

*References: stripped-operator-fixture-j63*

*Observed 2026-10-19 (python-dev)*
