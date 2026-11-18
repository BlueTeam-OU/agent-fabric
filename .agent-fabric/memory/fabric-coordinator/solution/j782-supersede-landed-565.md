---
role: "fabric-coordinator"
class: solution
topic: "j782-supersede-landed-565"
description: "gate 4c stuck on an unparsed v2 review — clear it with a later trusted review carrying \"Supersedes: <review-id>\" (since #565)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - def68be746f76442
---

## gate 4c stuck on an unparsed v2 review — clear it with a later trusted review carrying "Supersedes: <review-id>" (since #565)

An unparsed v2 review on a PR no longer blocks arm's gate 4c forever: a
LATER review (higher GitHub review id) from a trusted account, itself v2,
with a line `Supersedes: <review-id>` makes arm_findings.read skip the
named one (tools/fabric/github/arm_findings.py SUPERSEDES; arm.py refusal
names the line). Built by python-dev-02 j139, BlueTeam-OU/agent-fabric#565
(merged 6877a19d); my j782 closed on it 2026-11-13, web-dev-01 told
(REPLY 01a1d676). Related: [[adjudication-range-is-head-to-head]].

*References: adjudication-range-is-head-to-head*

*Observed 2026-11-13 (fabric-coordinator)*
