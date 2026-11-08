---
role: "python-dev"
class: solution
topic: "j207-assemble-foreign-root-merged-500"
description: "assemble.py without --fabric wrote domain slices to the tree AGENT_FABRIC_ROOT/OPERATOR named; refuse_foreign_root (#500); harvest/drain_due write no tree"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 36b4da1bb568f974
---

## assemble.py without --fabric wrote domain slices to the tree AGENT_FABRIC_ROOT/OPERATOR named; refuse_foreign_root (#500); harvest/drain_due write no tree

j207 (#500, merged 2026-11-07): the 2026-10-31 incident (29 domain slices, no project slice, in a source account's checkout) is explained by assembler/intake.py open_layout pinning the operator only under --fabric (j88, #460). Without it, layout.FABRIC_ROOT (AGENT_FABRIC_ROOT) and roots.operator_root (AGENT_FABRIC_OPERATOR) pick the domain/shared tree while --working-copy keeps project slices apart; domain-only landing is the signature. Fix: refuse_foreign_root exits 1 unless the variable's realpath is roots.code_root(). Measured: harvest_memory.py writes only .pyc beside loaded modules; drain_due writes state/jobs only. The 10-31 drain's actual environment was never seen: the cause is inferred.

**Why:** the owner asked "which step"; reading alone found nothing — a scratch-copy experiment (harvest, then assemble with each variable leaked) showed it.
**How to apply:** a "writes into the wrong tree" report: copy the tree twice, hash before/after, leak each root variable in turn. Test trap: a test of the accepted spelling needs a later error (unknown project) so the refusal's absence is observable. Future engine/operator split: every drain then needs --fabric.

*Observed 2026-11-07 (python-dev)*
