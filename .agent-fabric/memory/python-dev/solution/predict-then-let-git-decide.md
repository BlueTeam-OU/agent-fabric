---
role: "python-dev"
class: solution
topic: "predict-then-let-git-decide"
description: "a read-only prediction of a git pull's failure (fabric-fresh vs the launcher) must err toward refusing, and the actor must still let git decide"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf3131c5e836e5cb
---

## a read-only prediction of a git pull's failure (fabric-fresh vs the launcher) must err toward refusing, and the actor must still let git decide

fabric-fresh refuses (exit 3, --force or not) via `fabric_verdict` / `pull_blocker` in tools/fabric/launcher/currency.py (PR #214, j18). The launcher's `keep_fabric_current` acts on the same verdict but always runs `pull_ff` when behind: a file staged with the incoming content is "blocked" to the prediction and pulls fine.

**Why:** the review found the prediction wrong toward "go ahead" three ways (rename old path needs `--no-renames`, untracked dir needs `--untracked-files=all`, staged rename source is a separate `-z` field), then directory/file prefix collisions. A wrong "go ahead" ends a session that cannot relaunch.

**How to apply:** build such predictions from `diff --name-only --no-renames -z` and `status --porcelain -z --untracked-files=all`, compare with `/`-prefix tests, and check each case against a real `git pull --ff-only` in a throwaway repo. AGENT_FABRIC_ALLOW_STALE is the launcher's environment, not fabric-fresh's. Also: `fabric-pr arm` on a security-boundary path (launch.py, launcher/) under 8 work commits needs the owner's word or an architect-cto `AUTHORIZES:` id, not a coordinator request.

*Observed 2026-10-12 (python-dev)*
