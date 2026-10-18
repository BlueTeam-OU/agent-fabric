---
role: "language-culture"
class: workflow
topic: "cold-read-explore-on-sonnet"
description: "Холодное чтение готового текста — read-only Explore на model sonnet (не opus); locale-worker остаётся на opus"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7e7affc869878220
---

## Холодное чтение готового текста — read-only Explore на model sonnet (не opus); locale-worker остаётся на opus

fabric-coordinator's DECISION with the owner's word ("2 ok", 2026-10-10): a cold read — a fresh reader with no context judging whether a finished text reads naturally — is an Explore dispatched on `model: sonnet`. The dispatch guard does not ask for sonnet, so the owner is not prompted, at about a fifth of the cost. The locale-worker is unchanged: opus, as ADR-027 designs it. As of 2026-10-15 the rule is in no ADR, skill or slice. If a sonnet cold read misses something a stronger reader would have caught, send the example to fabric-coordinator: the rule changes on evidence.

*References: locale-worker-needs-model*

*Observed 2026-10-15 (language-culture)*
