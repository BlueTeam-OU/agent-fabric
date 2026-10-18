---
role: "fabric-coordinator"
class: threads
topic: "company-stores-j66"
description: "j66 / #271 (2026-10-15) — ADR-038 rule 10 company stores proposed; contract for python-dev; names inventory awaiting the owner; what the survey found"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f4c4f347022a226c
---

## j66 / #271 (2026-10-15) — ADR-038 rule 10 company stores proposed; contract for python-dev; names inventory awaiting the owner; what the survey found

PR BlueTeam-OU/agent-fabric#271 (branch develop-qzapp/user/feat/j66-engine-split-stage-3-adr-038):
ADR-038 rule 10 (A 2026-10-15), `docs/split/company-stores.md` (tooling contract, python-dev's lane
once accepted), `docs/split/company-store-names.md` (owner marks each row). Not armed: the owner accepts.

Survey facts (names only, from the coordinator store + 33 child mirrors in
~/.local/share/agent-fabric/children/): the company stores BlueTeam-OU/ and gzapi-org/agent-fabric-secrets
are private and EMPTY; edge-hosting holds BLUETEAM_DEPLOY_{HOST,USER,PASSWORD} it set itself 2026-10-11;
AGENT_FABRIC_READ_TOKEN is in my store and nothing in the tree reads it; GIT_SIGNING_KEY still makes
sync set commit.gpgsign (ADR-057 retirement unverified).

**Why:** the coordinator's own store holds company credentials that would die with its key (rule 4).
**How to apply:** after the owner's review, REQUEST python-dev with the contract; I supply clients.json
`operator` + lint onto its branch first. Related: [[agent-repo-per-agent]], [[threat-model-before-boundary-request]].

State 2026-10-15 end of session: #271 at 44439c22, 3 work + 11 fix; round 12 CLEAN (no findings), posted; gate waits on CI and the owner.
the PR (round 11 = review 5534897900). Design settled after round 8: one reading rule (start = newest
topological checkpoint of this store signed by a current holder, descending from the last verified
head; every later commit a current holder's; merges and other-client commits never verify), repair =
ordinary checkpoint, owner recover from a manifest-checked backup bundle, Proton session never in a
company store. Lesson: a
security contract written in prose drew a new P2 every round until the model was simplified to one rule.

*References: agent-repo-per-agent, threat-model-before-boundary-request*

*Observed 2026-10-15 (fabric-coordinator)*
