---
role: "fabric-coordinator"
class: threads
topic: "new-agent-first-credential-gap"
description: "new-agent.sh cannot create a brand-new account since ADR-038's stores: the child's store push runs before the child has any GitHub credential (its SSH key arrives later, from that same store); python-dev-01 stopped at step 5 on 2026-10-01"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 010ee174dba6c3e3
---

## new-agent.sh cannot create a brand-new account since ADR-038's stores: the child's store push runs before the child has any GitHub credential (its SSH key arrives later, from that same store); python-dev-01 stopped at step 5 on 2026-10-01

First real run of `runtime/provisioning/new-agent.sh` since the per-agent
stores replaced Doppler (python-dev-01, 2026-10-01, after #75 merged).
Steps 0–4 succeeded (account, claude 2.1.285, ori, host keys, https
clone). Step 5, `store-enroll.sh --born-now`, made the key and the store
(agent id 01a0f782-7e06-7dee-811f-0a860ed93bf3, key A02CB0F9…), and the
parent created the private repo
`gzapi-org/agent-fabric-secrets-01a0f782-…` (empty), then
`store push` AS THE CHILD failed: the child has no `~/.ssh` key — it
only gets one from `fabric-secrets sync`, i.e. from the store it cannot
push yet. Every earlier agent already had GitHub access (Doppler era)
when enrolled, so `test_new-agent.sh` (mocked) never met this.

**Why it matters:** no new agent can be provisioned until the first
credential has a delivery path. Ciphertext is safe to move by any
channel (entries are encrypted to the child's key), so the likely fix
is the parent pushing the initial store and handing the child its first
copy as a git bundle through the host executor, then SSH from there on —
a change to ADR-038 and store-enroll, the owner's to approve.

**Also:** `secret_store._run` reports git's LAST stderr line, which for
GitHub's not-found/no-access answer is "and the repository exists." —
the informative "ERROR:"/"fatal:" line is dropped. Prefer the last
`fatal:`/`ERROR:` line.

**How to apply:** resume with the same `new-agent.sh python-dev-01
python-dev --project agent-fabric` once the delivery path lands; every
step is idempotent and the id is already in the child's store. See
[[agent-owned-secrets-plan]], [[next-fabric-branch-queue]].

*References: agent-owned-secrets-plan, next-fabric-branch-queue*

*Observed 2026-10-01 (fabric-coordinator)*
