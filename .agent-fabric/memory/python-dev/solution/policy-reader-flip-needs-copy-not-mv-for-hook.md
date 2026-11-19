---
role: "python-dev"
class: solution
topic: "policy-reader-flip-needs-copy-not-mv-for-hook"
description: "j112 step A: flipping a checker's POLICY path before the file moves makes the pre-commit hook refuse; add a byte copy at the new path first"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 982dc64f80028da8
---

## j112 step A: flipping a checker's POLICY path before the file moves makes the pre-commit hook refuse; add a byte copy at the new path first

The pre-commit guard reads `state_writes.POLICY` etc. from the *working tree* modules and judges the staged blob at that path. Flip the constant while the file is still only under `policies/` and every commit touching a judged module is refused ("is not JSON"). A contributor cannot `git mv` out of `policies/` (outside its entry), so on j112 the flip commit also adds `tools/fabric/<x>.json` as a byte copy; the coordinator's later commit only removes the `policies/` originals.

Also: `tests/githook_fixtures.py` links every `tools/fabric/*` entry into its fixture fabric; a linked list is staged as link text (not JSON), so the nine lists are skipped there like `roots_bypass.json`.

**Why:** found when four commits in a row were refused by the hook (2026-11-12, branch feat/j112-adr-045-step-a-separate-what).
**How to apply:** order such a change as one commit carrying copy + flips; run `tests/test_githook_pre_commit.py` (99 tests) after, it is the only suite that notices fixture links.

*Anchors: `tools/fabric/state_writes.py::POLICY`, `tests/githook_fixtures.py::ENGINE_LISTS`*

*Observed 2026-11-12 (python-dev)*
