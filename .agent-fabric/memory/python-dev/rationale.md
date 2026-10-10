---
role: "python-dev"
class: rationale
description: "ADR-042 (signed store commits) — the coordinator's three rulings of 2026-10-04 that shape secret_store.py; read before touching store verification"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3897b9fb1a4ba672
  - befd542d338cc1c4
---

## ADR-042 (signed store commits) — the coordinator's three rulings of 2026-10-04 that shape secret_store.py; read before touching store verification

The rulings are in ADR-042 now (§5 rules 2 and 4, and the amendment of 2026-10-04) and in the code: `fabric-secrets store
trust-base` writes `agent-fabric.trustedbase` in the store's .git/config (tools/fabric/secret_store.py); writers
(lineage.json and identities/keys/<id>.asc) are read with `git show` at the fabric checkout's origin/main, never the
working tree (tools/fabric/secretstore/trust.py); take-bundle and seed-child record a base from a bundle
(tools/fabric/secretstore/mirrors.py). Do not restate them; read the record.

What the record does not carry, and a change near store verification should keep:
- **The base is explicit, never implicit.** An implicit "no base → take the local head" also fires on a hand-deleted
  mirror re-cloned from the remote, and would trust the remote whole. A store with no base refuses every verified
  operation and names the command that sets one.
- **The base is never in a commit.** It lives in the store's own .git/config: the remote could write a committed one.
- **seed-child records a base only when the mirror has none, only from a bundle, never from a fetch.** The child's
  first take-bundle (new_agent runs it before the keys PR merges) records its head as the base once, while the agent is
  absent from main's lineage; a second one before the merge refuses, naming "not yet on main".
- **No raw `git pull` on a store anywhere.** Every enrolment makes and updates the parent's mirror through the store tool
  (bundle | seed-child); a re-run updates it by the verified fetch.

*Observed 2026-10-10 (python-dev)*
