---
role: "fabric-coordinator"
class: workflow
topic: "fold-then-full-suite"
description: "After folding a contributor's branch, run tests/run.sh python, not a hand-picked list: #242 went red on test_pr_counts.py, which I had not run"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7bd8bb2770c82959
---

## After folding a contributor's branch, run tests/run.sh python, not a hand-picked list: #242 went red on test_pr_counts.py, which I had not run

2026-10-13, #242: I folded devex-tooling's for/user/arm-merged-readback (a15e5126 changed the
pr_counts line to per-engine "review claude ✓ codex ✗") and ran a hand-picked set of suites
(arm_cli, pr_gate, wait_merged…), all green. tests/test_pr_counts.py, which still expected "head
reviewed", was not in my list; platform-smoke failed it after I had armed, blocking the merge and
costing a contributor round trip and a re-arm.

**Why:** a contributor's change reaches tests I did not think of; the suite knows, my list does not.
**How to apply:** after a fold or a merge of main into my branch, run `tests/run.sh python` (or the
platform-smoke steps) in the branch's own tree before pushing and arming; a hand-picked list is for
the inner loop only. Related: [[lint-in-worktree-root]].

*References: lint-in-worktree-root*

*Observed 2026-10-13 (fabric-coordinator)*
