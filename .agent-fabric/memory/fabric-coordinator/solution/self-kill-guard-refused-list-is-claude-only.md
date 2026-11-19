---
role: "fabric-coordinator"
class: solution
topic: "self-kill-guard-refused-list-is-claude-only"
description: "Adding a self-kill-guard test for an inbox-watch pattern — the `refused` list only checks claude's command line, not the watch models"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 347da10d7619e0a7
---

## Adding a self-kill-guard test for an inbox-watch pattern — the `refused` list only checks claude's command line, not the watch models

In tests/test_self_kill_guard.py the `refused` list runs `g.verdict(cmd, CLAUDE)`, and that judges a pattern against the claude process's command line only. A pattern that only an inbox-watch model (INBOX_MODELS) carries fails there even when the guard refuses it. Test such a pattern through `g.decision(cmd, CLAUDE)` and bracket it (`[g]zcoord inbox`) so that only the model, not the command's own text, can match. Found on j741, commit 21deaa90 on #546.

Also from j741: running `tools/fabric/lint.py` from a worktree under projects/ also lints the sibling checkouts' memory corpus. Those "corpus lint: N finding(s)" lines are not the branch's. Check a file with `git ls-files --error-unmatch` before reading it as yours.

Related: [[tests-and-suite]], [[lint-in-worktree-root]].

*References: lint-in-worktree-root, tests-and-suite*

*Anchors: `tests/test_self_kill_guard.py::refused = [`, `runtime/claude-code/hooks/self-kill-guard.py::INBOX_MODELS`*

*Observed 2026-11-10 (fabric-coordinator)*
