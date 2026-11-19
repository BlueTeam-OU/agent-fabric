---
role: "fabric-coordinator"
class: rationale
topic: "operator-engine-pin-decided"
description: "Where the operator repository pins the engine (ADR-045 §6), decided 2026-11-12 for python-dev-01's j229; awaits an ADR-045 amendment"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27ceceb9599d316b
---

## Where the operator repository pins the engine (ADR-045 §6), decided 2026-11-12 for python-dev-01's j229; awaits an ADR-045 amendment

Decided 2026-11-12 (REPLY 01a1cf0f-e895 to python-dev-01, j229, answering their proposal 01a1cf0c-b648):
- The pin is `.agent-fabric/fabric-ref` in `BlueTeam-OU/blueteam-fabric`: one line, the full 40-hex engine sha. It is ADR-011's shape. There is no tag field, because a tag would be a second truth.
- One reader enforces it, for both the upgrade and the launcher's pull. The engine fast-forwards to the pin and never past it. A pin the engine cannot reach after a fetch is reported, and the engine stays where it is.
- An absent operator checkout or absent fabric-ref keeps today's behaviour (track origin/main) and prints one report line. Python-dev-01 proposed freezing instead, but the repository is empty until step C, so a freeze would stop every upgrade. A pin that is present but malformed is refused.
- Still open, and mine before step D: how the pin moves on each distribution (who commits it, and whether `fabric-ctl all upgrade fabric` moves it).

**How to apply:** write this as an ADR-045 amendment on the j766 PR. The message is not the record. Related: [[adr-067-wave-3-started]].

*References: adr-067-wave-3-started*

*Observed 2026-11-12 (fabric-coordinator)*
