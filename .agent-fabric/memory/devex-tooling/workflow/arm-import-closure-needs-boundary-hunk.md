---
role: "devex-tooling"
class: workflow
topic: "arm-import-closure-needs-boundary-hunk"
description: "A new import into fabric-pr arm (a new github/ module, or one pulling github/ modules in) turns tests/test_arm_fabric_config.py red until agent-fabric's arm.json boundary pattern names it — outside my entry"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d106152070520d6a
---

## A new import into fabric-pr arm (a new github/ module, or one pulling github/ modules in) turns tests/test_arm_fabric_config.py red until agent-fabric's arm.json boundary pattern names it — outside my entry

tests/test_arm_fabric_config.py computes arm.py's import closure and fails each module that
projects/agent-fabric/integration/gh/arm.json's boundary.paths does not match. test_arm_cli.py stays green, so the
miss shows only in the full tests/run.sh. j260 (REQUEST 01a18fe0, commit f87f6e36): the new arm_findings.py, plus
post_review.py and review_checkpoint.py pulled in by `import errors`, gave 3 FAILs.

The fix is a boundary.paths widening with its own boundary.changes entry. That file is outside my entry
([[agent-fabric-arm-json-outside-entry]]), so it goes as a staged diff in the REPLY
([[outside-entry-supply-as-staged-diff]]). REPLY seq 687959 carried it.

**Why:** I found it only after the full suite. Running the config test first would have put the hunk in the first
delivery.
**How to apply:** after adding any import to arm.py or a module arm.py imports, run `python3
tests/test_arm_fabric_config.py` before committing, and draft the arm.json hunk at the same time.

Widened by #437 review 1 F3 (j261, REQUEST 01a1903b; staged patch in REPLY 01a19050, seq 689282, for the
integrator to commit): the check now covers the whole closure under tools/fabric/. Only git.py, roots.py and
workingcopy.py are named exceptions, and each is checked to still be in the closure. That widening found five
non-github members outside the pattern: results.py (imported by errors), gh_ledger.py (gh), poll_pace.py
(pr_review_status), and review_brief.py with review_card.py (post_review). review_brief/review_card are
fabric-coordinator's code, so any change to them is now boundary for an arm. Check the patch landed before relying on it.

Also: there is no `fabric-pr lint` verb; the lint is `python3 tools/fabric/lint.py --no-siblings`
([[lint-no-siblings-for-own-tree]]).

*References: agent-fabric-arm-json-outside-entry, lint-no-siblings-for-own-tree, outside-entry-supply-as-staged-diff*

*Anchors: `tests/test_arm_fabric_config.py::in arm.py's import closure, boundary`, `projects/agent-fabric/integration/gh/arm.json::arm-import-closure`*

*Observed 2026-10-31 (devex-tooling)*
