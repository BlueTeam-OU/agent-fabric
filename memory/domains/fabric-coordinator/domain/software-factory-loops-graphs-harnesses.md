---
role: "fabric-coordinator"
class: domain
topic: "software-factory-loops-graphs-harnesses"
description: "Ivo Kund's \"software factory\" (2026-09-11) — planning and execution loops, a dependency graph, a harness, an outer loop; what it claims and where the fabric already matches"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 363690827d46bc58
---

## Ivo Kund's "software factory" (2026-09-11) — planning and execution loops, a dependency graph, a harness, an outer loop; what it claims and where the fabric already matches

Source: https://www.ivokund.com/loops-graphs-harnesses-getting-quality-out-of-a-software-factory/
(part 2; part 1 is about alignment). Read 2026-10-09 at the owner's request; external
text, its claims are the author's, not measured here.

Claims, in its words where they define something:
- Quality comes from the control layer ("harness"), not the model: two loops (plan →
  specs; specs → code → shipped) plus an outer loop that turns every failure into a
  process change. Separating creating work from doing work was the biggest gain.
- "Validation is the bottleneck": choose the human chokepoints explicitly (plan
  changes, infra/data-model, outer-loop changes); never hand-review what the harness
  can, never fix output by hand — "fix the machine, not the output".
- Shift validation left: ~1M tokens/issue on planning vs ~0.5M on build. Parallel
  critics from different vendors review each issue until no high-severity finding.
- An issue carries: original user intent WITH NON-GOALS (its most valuable lesson —
  without it scope drifted), acceptance criteria, and validation steps mapping each
  criterion to a tier (unit, E2E, agent in local browser, agent in prod).
- Failure mode: a summarizer rewriting the ticket each critique round erased which
  requirements were original → scope drift. Fix: append feedback under its own
  section; synthesize v2 once at the end, against the original intent.
- Enforce over document: deterministic checks in code, not prompts (dead-code
  removal, complexity caps, max type strictness, executable specs).
- Execution: dependency graph → 3–4 batches, parallel per-ticket worktrees, a
  reviewer agent with evidence (screenshots), sequential integration in dependency
  order, then a final test round. Parallelism is capped by RAM (Chromium), not models.
- Every run ends in a handoff file of what went wrong; a planning agent verifies and
  feeds it into the next planning loop — "the step that compounds".
- Escalate more rather than less while agents cannot absorb surprises.

Where the fabric already matches: the review class as the review, owner arming as a
chosen chokepoint (ADR-019/020); guards = hook + CI + suite (enforce over document);
worktree isolation; fabric-lease for host resources; review briefs' out_of_scope.
Candidate gaps are in [[software-factory-gaps-2026-10-09]].

*References: software-factory-gaps-2026-10-09*

*Observed 2026-10-09 (fabric-coordinator)*
