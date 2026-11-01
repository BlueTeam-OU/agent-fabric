---
role: "python-dev"
class: solution
topic: "stripped-gateway-plan-fixture-j62"
description: "j62 fix for test_gateway_plan on a stripped copy: operator tree with the routing overlay, plus a role layer; skip-list line leaves with the fix"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2d0680b10bff6790
---

## j62 fix for test_gateway_plan on a stripped copy: operator tree with the routing overlay, plus a role layer; skip-list line leaves with the fix

j62 (branch develop-qzapp/python-dev-03/feat/j62-stripped-nightly-red-tests-test-gateway, dba15c0b): tests/test_gateway_plan.py ran gp.build against the live routing/profiles.json, which a stripped copy lacks. It now makes a temp AGENT_FABRIC_OPERATOR with the engine's routing copied via ROUTING_OPERATOR_IGNORE plus instance_fixtures.write_routing_overlay, and sets it for the in-process calls and the CLI children's env.

**Why:** the frozen routing-distinct profile has empty roles, so any case asserting a role changes the session model needs the test to add a role layer to its own copy of profiles.json.
**How to apply:** for a routing-reading test, copy this pattern (tests/test_routing.py, test_model_profile.py use it); when #304's tests/stripped_skip.txt is on main, the fixing commit removes the file's line from it or the nightly fails. A #304-type review finding that a negative case passes for the wrong reason (a path that does not exist yet) is answered by creating the real file first and showing the mutation fails it.

*Observed 2026-10-19 (python-dev)*
