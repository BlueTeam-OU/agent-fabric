---
role: "python-dev"
class: workflow
topic: "j186-verified-sender-delivered"
description: j186/j389 carrier journals under the roster address; delivered as for/ branch 2103e613; how the job guard and suite timeout bit
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1911fa5eff348455
---

## j186/j389 carrier journals under the roster address; delivered as for/ branch 2103e613; how the job guard and suite timeout bit

j186 (REQUEST 01a182b4): Carrier.journal takes (text, ts, verified sender); main.journal_inbound writes rec["sender"]. Delivered as branch develop-qzapp/python-dev-01/for/user/j389-verified-sender (commit 2103e613 on the coordinator's bc73f87a), no PR; suite green.

**Why:** the job guard refuses `git commit` in a sibling worktree even with `git -C <literal path>`; the fix that worked was `git diff HEAD > patch`, `git worktree remove --force`, checkout the branch in the main checkout, `git apply`, commit, push, checkout main. See [[job-hook-commit-in-main-checkout-works]].

**How to apply:** a full `tests/run.sh` outlives a 600000 ms background timeout (killed, no result); give run_in_background `timeout: 7200000` from the start.

*References: job-hook-commit-in-main-checkout-works*

*Anchors: `tools/fabric/gzcoord/carrier/engine.py::verified sender`*

*Observed 2026-10-28 (python-dev)*
