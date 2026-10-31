---
role: "python-dev"
class: solution
topic: "review-mcp-sandbox-binds-j154"
description: "review_mcp sandbox bind rules (#358 round 3), the etc=/usr= seams, and the job-switch trap after a follow-up request lands"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 20c792f3424fc329
---

## review_mcp sandbox bind rules (#358 round 3), the etc=/usr= seams, and the job-switch trap after a follow-up request lands

sandbox.py binds named cert paths only (ETC_RO relative to `etc=`), drops /opt, masks /usr/local with a tmpfs and gives back the pin PREFIX plus a recreated fabric-python symlink; KEY_DIRS (relative to `usr=`) are tmpfs masks, not binds. A tmpfs on a path absent in the ro-bound /usr makes bwrap fail, so the Debian mask cannot be run live on Fedora: assert it at argv level with a `usr=` fixture. Tests that scan argv for "private" must read bind verbs only (CI debian failed on the mask, e67e5c8e).

**Why:** j154 delivered edf3fd5d; j155 is the Debian CI follow-up; patch parked at ~/agent-fabric-tmp/j155/debian-mask.patch (applies to e67e5c8e).

**How to apply:** after `fabric-jobs deliver`, a PreToolUse hook refuses `git commit` in that session (ADR-037 rule 3) even when a follow-up REQUEST arrives; `switch` then wants a clean worktree. Park uncommitted work as a patch outside the session scratchpad, revert, switch, apply in the fresh session. Better: do not deliver until the CI of the folded head is read.

*Anchors: `tools/fabric/review_mcp/sandbox.py::KEY_DIRS`, `tests/test_review_mcp.py::no source or destination of any bind`*

*Observed 2026-10-24 (python-dev)*
