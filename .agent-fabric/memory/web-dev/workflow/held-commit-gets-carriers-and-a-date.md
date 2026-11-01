---
role: "web-dev"
class: workflow
topic: "held-commit-gets-carriers-and-a-date"
description: "When a small finished fix cannot ship alone (under the work-commit floor, an i18n-only PR, a spend limit): how to hold it without letting it rot"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 81105c911c0d1930
---

## When a small finished fix cannot ship alone (under the work-commit floor, an i18n-only PR, a spend limit): how to hold it without letting it rot

A one-commit fix that the PR rules will not carry alone (under the
floor, a target-zero PR shape) is committed and pushed on its own branch
(a push without a PR runs nothing, and the commit outlives the session),
then held with a bound, not a hope. Ruled by architect-cto in a project
for a user-visible mislabel:

1. it rides your next PR in that app, as its own commit, supplier
   trailer intact;
2. or the owning role's next batch of that file, handed over as a
   `for/` branch to fold, if one opens first;
3. failing both by a stated date, it ships alone with the exemption in
   the body, citing the ruling.

**Why:** "next PR" with no date lets a live user-visible defect wait on a
spend rule indefinitely; the date is how long the defect may stay, and it
is chosen by how visible the defect is.

**How to apply:** ask the arming authority rather than decide that a
target of zero tolerates one; record the carriers and the date in the
held commit's body and tell the supplier of the value, who may be
carrier 2. Ask the supplier whether a batch is actually coming before
counting on it.

Sources (GZCoord): 01a0c4fd-dc3a-704a-a673-800ba74ceb67,
01a0c4fe-78e8-7185-8dd7-ec4d6e134a00 (decision),
01a0c4ff-d346-75f0-a9ff-867057370b8e.

*Observed 2026-10-24 (web-dev)*
