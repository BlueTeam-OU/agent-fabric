---
role: "python-dev"
class: solution
topic: "j88-test-arm-policy-path-name-merged"
description: "A test failing only from some checkout paths - suspect the path's NAME matching a stub's substring dispatch before its length; reproduce from a directory named for the suspect"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f4694a486cb10482
---

## A test failing only from some checkout paths - suspect the path's NAME matching a stub's substring dispatch before its length; reproduce from a directory named for the suspect

BlueTeam-OU/agent-fabric#359 merged (1 work, 1 fix). tests/test_arm_policy.py failed 70 cases from a worktree path holding "fabric-ctl" because the reader stub matched substrings on the full argv (path included). 487807fb already fixed the dispatch (basename + verb); #359 adds the pin (ArmRun, arm.FABRIC patched to a path naming fabric-ctl, gzcoord-inbox, fabric-whoami; assert rc 0 and `reads == []`). Paths of 170-698 bytes pass: no length bound.

**Why:** a finding reported as "long path" was a name collision; reproduce with a directory NAMED for the suspect, not just a long one.
**How to apply:** a stub that routes on argv must key on program name and verb. Open: ArmRun does not clear AGENT_FABRIC_PR_* reader overrides (suite red when AGENT_FABRIC_PR_REVIEW_STATUS is set; CI does not set them). Re-review needs card_base (first round's base) and previous_findings as a file.

*Anchors: `tests/test_arm_policy.py::a_checkout_path_that_names_a_reader`*

*Observed 2026-10-24 (python-dev)*
