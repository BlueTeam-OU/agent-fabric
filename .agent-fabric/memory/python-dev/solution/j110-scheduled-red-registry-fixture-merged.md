---
role: "python-dev"
class: solution
topic: "j110-scheduled-red-registry-fixture-merged"
description: "j110 #466 merged; tool reads registry under AGENT_FABRIC_OPERATOR, plant an id absent from the live registry"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 98b1d9a67d140795
---

## j110 #466 merged; tool reads registry under AGENT_FABRIC_OPERATOR, plant an id absent from the live registry

#466 merged 2026-11-03 on head f530aec3 (2 work, 1 fix): tests/test_scheduled_red.py plants a registry via write_registry under AGENT_FABRIC_OPERATOR (AGENT_FABRIC_ROOT is also the engine root, so pointing it at a fixture breaks the tool's imports). Plant an id the live registry lacks (fixture-proj) or the test cannot tell the readers apart (review F1). Carried the coordinator's timer commit 5784af63; a timer file is a boundary file, so arm needed the owner's word. review_brief re-review refuses previous_findings for a PR; use tools/fabric/review_brief.py render directly (fabric-review brief wrapper only printed usage).
**Why:** stripped nightly reds from live-registry reads. **How to apply:** any test resolving repos/projects plants its registry under OPERATOR with an id not in projects/registry.json.

*Observed 2026-11-03 (python-dev)*
