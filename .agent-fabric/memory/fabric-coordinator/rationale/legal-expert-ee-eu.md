---
role: "fabric-coordinator"
class: rationale
topic: "legal-expert-ee-eu"
description: "Owner 2026-10-15 — new agent legal-expert-ee-eu, role legal-expert (jurisdiction in the login suffix), persona surname Kelsen, serves agent-fabric first (j241)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7bd0625179c6eae3
---

## Owner 2026-10-15 — new agent legal-expert-ee-eu, role legal-expert (jurisdiction in the login suffix), persona surname Kelsen, serves agent-fabric first (j241)

The owner, 2026-10-15, in the coordinator's session: "we need to add a legal-expert-ee-eu surname Kelsen,
an expert of law of Estonia and EU". Answers to my questions: a NEW generic role `legal-expert`, the
jurisdiction carried by the login suffix (`-ee-eu`, as language-culture-ge/-ru/-en carry a locale);
first project agent-fabric (Blueteam); after #271 round 2.

Kelsen = Hans Kelsen (Austria, 1881-1973, legal theorist, Pure Theory of Law): passes the
surnames.json rule (deceased, no weapon work), but is a jurist, not a natural scientist — the list says
"scientists"; state the owner's choice in the entry. First name from Austria's culture.

State 2026-10-15 15:00Z: role commits 4d0c4a36 (charter, recall, catalogue) and d1a4410d (remit,
taxonomy, docs/legal/ contributor entry, placement, Kelsen with a `note`) pushed on #271's branch;
review round 1 dispatched. new-agent.sh refuses a role that is not on main (dry run): provision only
after #271 merges; the claim (keyed by agent id) and first name come from the new agent itself.
Open question for the owner: which Claude account (claude-pzhuy-8alias-com or andrea-benetton).

**How to apply:** j241 — role charter/brief + catalogue + taxonomy, surnames.json entry + claim,
new-agent.sh legal-expert-ee-eu legal-expert --project agent-fabric. Related: [[agent-persona-decisions]].

*References: agent-persona-decisions*

*Observed 2026-10-15 (fabric-coordinator)*
