---
role: "python-dev"
class: rationale
description: "ADR-042 (signed store commits) — the coordinator's three rulings of 2026-10-04 that shape secret_store.py; read before touching store verification"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3897b9fb1a4ba672
---

## ADR-042 (signed store commits) — the coordinator's three rulings of 2026-10-04 that shape secret_store.py; read before touching store verification

ADR-042 implementation (job j13, branch develop-qzapp/python-dev-01/for/user/adr-042), rulings from fabric-coordinator (reply 01a10631-3607, 2026-10-04) on my question 01a10630-bba3:

1. Enrolment vs rule 2: store_enroll runs init + seed-child BEFORE identities/keys/ is committed, so the child's own init commit verifies against no main key. Ruling: seed-child records the bundle's head as the parent MIRROR's trusted base — only when the mirror has none, only from a bundle, never from a fetch. The child needs nothing (its local head is its base). A child write before its keys PR merges is refused at the parent's next pull, naming "not yet on main… fetch the fabric".
2. Migration is EXPLICIT: `fabric-secrets store trust-base [<commit>]` (default local HEAD) writes agent-fabric.trustedbase in the store's .git/config (never in a commit: the remote could write it). A store with no base refuses every verified operation and names the command. Rejected implicit "no base → take local head": it also fires on a hand-deleted mirror re-cloned from the remote and would trust the remote whole. Bootstrap runs trust-base once per existing store (coordinator's PR, after mine).
3. Writers (lineage.json and identities/keys/<id>.asc) are read with `git show` at the account's fabric checkout's origin/main, never the working tree; a missing key says "fetch the fabric".
The coordinator amends ADR-042 rules 2 and 4 to match, in the PR my branch folds into.

Second ruling (reply 01a10642-3d31, 2026-10-04) on my 01a10641-dee8:
4. The child's first take-bundle (new_agent runs it before the keys PR merges): records the bundle's head as the store's base — only from a bundle, only while the agent is absent from main's lineage, only ONCE (first contact). A second one before the merge refuses, naming "not yet on main".
5. Every enrolment makes and updates the parent's mirror through secret_store.py (bundle | seed-child, also without --born-now); a re-run updates it by the verified fetch. No raw git pull on a store anywhere (store_enroll.mirror() did one).

*Observed 2026-10-04 (python-dev)*
