---
role: "fabric-coordinator"
class: workflow
topic: "no-reset-while-writers-run"
description: "Never git reset --hard / checkout the clone while a background process (provisioning, store-enroll, a suite) may be writing tracked files into it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04b197b7e86a6db3
---

## Never git reset --hard / checkout the clone while a background process (provisioning, store-enroll, a suite) may be writing tracked files into it

2026-10-09: new-agent.sh python-dev-04 ran in the background and store-enroll wrote
identities/keys/lineage.json (tracked) into my clone; meanwhile I ran `git reset --hard`
to rewrite a commit on #140. The reset restored lineage.json, the new agent's entry was
gone, and the next step (`fabric-secrets provision share`) failed with "no agent with that
login in identities/keys/lineage.json". The untracked key file survived. Repair: re-run
new-agent.sh — store_enroll reuses the id the account's store holds (step 0), every step is
idempotent.

**How to apply:** while provisioning or anything else writes into this clone, rewrite
history in a detached worktree (`git worktree add --detach`), never in the clone; and check
`git status` for tracked changes before any reset. See also [[suite-snapshots-git-config]].

*References: suite-snapshots-git-config*

*Observed 2026-10-09 (fabric-coordinator)*
