---
role: "python-dev"
class: workflow
topic: "origin-sweep-and-review-rounds-j92"
description: "j92 #416 — fabric-branches deletes own merged origin branches; leased delete, oracle edit, supply fold, review-round tooling traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 598e411aa65d37b2
---

## j92 #416 — fabric-branches deletes own merged origin branches; leased delete, oracle edit, supply fold, review-round tooling traps

#416 merged 2026-10-28 (head 9ae775f2): `branches.py remote_sweep` judges the tip from `git ls-remote` (a fetch without --prune keeps refs of deleted branches), deletes with `git push --force-with-lease=refs/heads/<b>:<tip> --delete`; the lease test needs a fake gh that pushes during the PR lookup. Exit 1 now also means a refused origin delete; `sweep_all` appends a note. The old CLI oracle's "no remote branch is touched" had to change (the contract changed) — name that in the PR body.

Review-round tooling: coordinator's supply (ADR/skills) arrives as a `for/` branch — fold with `git merge` of it, then `git merge origin/main`, rerun the suite, review the final head once. `fabric-review next` needs `fabric-review save <pr> <round> --repo <dir-name> < report` for every round that was POSTED, and the request must be the previous round's derived `req-rrN.json` (the original request errors "starts at its last review's head"); add `card_base:` (round-1 base_sha) to the first request. A subagent can Read the brief file instead of receiving it pasted. A `pgrep -f` watcher matches itself; wait on a log marker line that cannot appear mid-run (`^RUNEND`), not `^exit `.

**Why:** cost several wrong-path retries. **How to apply:** save each posted round, keep req-rrN.json, strip AGENT_FABRIC_*/GITHUB_* for run.sh (test_launch, test_launch_cli, test_launcher_gateway are red on clean main in this account).

*Anchors: `tools/fabric/branches.py::remote_sweep`*

*Observed 2026-10-28 (python-dev)*
