---
role: "devex-tooling"
class: workflow
topic: "arm-policy-test-patches-config-loader"
description: "A second read of arm.json in fabric-pr arm (beside load_config) reds tests/test_arm_policy.py: it patches load_config and sets config_path to a dummy 'x' that does not exist"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3f7cc4c4a197927d
---

## A second read of arm.json in fabric-pr arm (beside load_config) reds tests/test_arm_policy.py: it patches load_config and sets config_path to a dummy 'x' that does not exist

tests/test_arm_policy.py (not in my entry) replaces arm.load_config and gives config_path() the path "x", which does
not exist. j291 (record path, REQUEST 01a1aa92) added arm_rules.load_record_rules, which opens that path itself. It
raised Unanswered on FileNotFoundError, and four direct-mode ArmRun cases failed. test_arm_cli stayed green, so this
showed only in the full tests/run.sh.

The fix (commit 220585bc): a FileNotFoundError there returns None. load_config has already refused a missing file
in a real run, so None (no record path, every gate kept) is the safe reading.

**Why:** the in-process suites mock the loader, not the file. A new reader of the same file is not covered by
their mock.
**How to apply:** when arm reads anything new from arm.json, run tests/test_arm_policy.py beside
test_arm_cli and test_arm_fabric_config before committing ([[arm-import-closure-needs-boundary-hunk]]). Make the new
read degrade to the gate-keeping default when the file is absent.

*References: arm-import-closure-needs-boundary-hunk*

*Anchors: `tests/test_arm_policy.py::"config_path", return_value="x"`, `tools/fabric/github/arm_rules.py::def load_record_rules`*

*Observed 2026-11-05 (devex-tooling)*
