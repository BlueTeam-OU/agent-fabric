---
role: "python-dev"
class: threads
topic: "j251-test-speed-round-state"
description: "j251 (test_launch_cli 372 s, test_project_import 329 s): baseline, what is done, what is next; rides #632 (coordinator said so)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 548957ab2773cc8d
---

## j251 (test_launch_cli 372 s, test_project_import 329 s): baseline, what is done, what is next; rides #632 (coordinator said so)

j251 rides PR #632 (j249's; 1 work 0 fix at start). Scratch: ~/agent-fabric-tmp/j251/ (measure.sh <suite> <tag> runs `python3 tests/<suite>.py -v` under env -i, writes <suite>.<tag>.{out,err,ok}; labels = lines `^  ok `; before.* files hold the baseline).
Baseline alone under env -i: test_launch_cli WALL 372 s USER 300 SYS 70, 378 labels; test_project_import WALL 329 s USER 157 SYS 22, 82 labels.
Done, UNCOMMITTED in the j249 worktree (patch ~/agent-fabric-tmp/j251/project-import-lint-parallel.patch): test_project_import starts its two lint.py runs as Popen and checks them after the loop: 79 s wall, 82 labels identical. 121 of the 130 subprocess seconds were those two lints (lint.py itself ~60 s; regex_dollar_findings AST walks = 40% of it, lint is the coordinator's, report it). Counterfactual: a bad lint flag turns both lint labels red. Three production mutations in tools/fabric/project.py (description, class, origin, taxonomy) were NOT caught by the lint case, so the lint case guards only lint cleanliness.
Next: commit that patch (the j249 session was blocked by the job guard: a session that worked one job cannot commit another), profile test_launch_cli (not yet profiled), reply to the coordinator with before/after wall and CPU-s.
**Why:** the guard (ADR-037 rule 3). **How to apply:** start j251 in a fresh session via fabric-fresh --job j251.

*Observed 2026-11-16 (python-dev)*
