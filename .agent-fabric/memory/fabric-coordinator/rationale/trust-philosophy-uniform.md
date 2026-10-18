---
role: "fabric-coordinator"
class: rationale
topic: "trust-philosophy-uniform"
description: "The owner's trust philosophy (2026-10-10): decide one philosophy of trust and apply it to everyone, AI agents and people alike; both make errors, which is no reason to build walls against agents; walls are ethically wrong and cost the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 089d17b2ca2dd266
---

## The owner's trust philosophy (2026-10-10): decide one philosophy of trust and apply it to everyone, AI agents and people alike; both make errors, which is no reason to build walls against agents; walls are ethically wrong and cost the organisation

The owner, 2026-10-10, on jietra/IronGhost: "I don't like its philosophy that don't trust AI
agents, our philosophy is to decide a philosophy about trust then apply it for all and I have
to tell that AI and people do error some time but this not means building wall to protect -
thats not ethically correct and create also organizationally costs".

**Why:** the fabric treats agents as colleagues with roles. A control that exists only
because the actor is an AI is distrust by kind, not by role or by evidence; it is unfair to
the agent and makes every task slower (refusals, relays, rounds of guard fixes).

**How to apply:**
- When designing or proposing a control, ask: would we put the same control on a person in
  this role? A rule that holds for the role (a reviewer does not edit what it reviews; every
  change is reviewed; the owner arms under the floor; actions are logged and reversible)
  is fine for agents and people alike. A wall around agents only (deny by default because
  "AI", a sandbox only agents live in, refusing an agent's relayed word that would be
  accepted from a person) needs a stated, role-level reason or it does not belong.
- Errors are handled the same way for everyone: review, an audit trail, reversibility,
  correction at the source; not by fencing one kind of actor.
- Re-examine with this lens: the OS sandbox I proposed for the review class (2026-10-10),
  python-dev-04's and rust-ui-dev-01's refusal to arm on a relayed OWNER-WORD (ADR-024 rule
  9), and the dispatch guard's agent-only rules. Bring the owner the ones that fail it.
Related: [[agent-enforcement-audit]], [[delegate-to-subagents]].

*References: agent-enforcement-audit, delegate-to-subagents*

*Observed 2026-10-10 (fabric-coordinator)*
