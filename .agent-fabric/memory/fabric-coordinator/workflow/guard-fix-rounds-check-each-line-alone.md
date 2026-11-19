---
role: "fabric-coordinator"
class: workflow
topic: "guard-fix-rounds-check-each-line-alone"
description: "When a guard fix adds two lines for one finding, mutate each alone before pushing — a second line \"for safety\" can reopen a refusal the base made (#637 round 6 F22)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 973b3c2f0a0b8d35
---

## When a guard fix adds two lines for one finding, mutate each alone before pushing — a second line "for safety" can reopen a refusal the base made (#637 round 6 F22)

#637 (j830/j914, merged 8c4f604f 2026-11-17) took 8 review rounds on the post-review and self-kill guards. Round 5's F19
fix (92cb287b) added two lines: an `EXEC_FLAGS` check and an operand-count restore. The EXEC_FLAGS line alone closed F19;
the restore line was unneeded and let `runuser -u me sg test "$c" post-review 1 < r.md` pass, which the base refused
(round 6 F22, P2). Its test comment also claimed a mutation the suite did not catch (F23).

**Why:** each round's fix in this PR opened the next round's finding; a reviewer's mutant of each line alone found it.
**How to apply:** before pushing a guard fix, mutate every added line alone and confirm a named case fails for each
(drop a line no case needs); run a base-vs-head differential on the refused list. A codex timeout/ReDoS finding on
crafted input: cap the work and fail closed, pinned by a count-based case, never a wall-clock one (host at load 45).
`fabric-review next --adjudicate` refuses the last checkpoint head: the next re-review is what judges its findings,
and the claude brief carries only claude's findings, while the arm gate still read "no finding open" after round 8.

*Observed 2026-11-17 (fabric-coordinator)*
