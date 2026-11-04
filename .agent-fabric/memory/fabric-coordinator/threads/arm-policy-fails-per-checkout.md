---
role: "fabric-coordinator"
class: threads
topic: "arm-policy-fails-per-checkout"
description: "test_arm_policy fails 70/168 in one worktree, passes in another on the same code; not path length alone (j353 evidence, 2026-10-22)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d6676cbc96562e55
---

## test_arm_policy fails 70/168 in one worktree, passes in another on the same code; not path length alone (j353 evidence, 2026-10-22)

2026-10-22, j353 evidence. `python3 tests/test_arm_policy.py` at #355's code:
- worktree ~/projects/agent-fabric-j349-owner-2026-10-22-fabric-ctl (65 chars, branch
  checked out or detached, with or without the j349 bootstrap commit d61668c3): FAILED (failures=70).
- detached worktree ~/projects/agent-fabric-j349-ctrl-armpolicy-head-1d8324c8xx (77 chars,
  LONGER) at 1d8324c8: OK.
Failure shape: rc is the string `unanswered: pr-review-status --json carr…` instead of 0, so the
fixture's fake pr-review-status goes unanswered. The "long path" theory (python-dev-02, INFO 01a16480)
does not fit: the shorter path fails. Next: diff the two worktrees' git config, untracked
files and env reads in the fixture. The control worktree was swept by fabric-jobs switch the same day;
recreate it with `git worktree add --detach <long path> 1d8324c8`. Reported to python-dev-01 in REPLY 01a164e0.

*Observed 2026-10-22 (fabric-coordinator)*
