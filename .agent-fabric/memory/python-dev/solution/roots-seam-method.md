---
role: "python-dev"
class: solution
topic: "roots-seam-method"
description: "How the engine/operator roots seam (tools/fabric/roots.py, runtime/control/roots.mjs, PR #119) was built and what the review found — the engine= trap and fixture rules"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6d23ea75be0c1d75
---

## How the engine/operator roots seam (tools/fabric/roots.py, runtime/control/roots.mjs, PR #119) was built and what the review found — the engine= trap and fixture rules

`tools/fabric/roots.py` / `runtime/control/roots.mjs` (agent-fabric #119, ADR-045 §5 rules 1-3): `engine_root()` honours AGENT_FABRIC_ROOT (legacy; ADR says the code's location), `operator_root()` is AGENT_FABRIC_OPERATOR else the engine root. Helpers take `root=` (explicit operator tree, wins), `engine=` (the engine tree the caller was handed; the operator still outranks it) and `environ=`.

**The trap the blind review found:** a reader that took its tree from its OWN location (`ROOT = dirname(__file__)`...) must pass `engine=<that>`; moving it onto `roots.x()` plain makes it follow AGENT_FABRIC_ROOT, a behaviour change wherever the variable names another clone (this very session's). Pin each `engine=` with a test run with AGENT_FABRIC_ROOT at an empty tree and no operator — deleting the `engine=` must fail it (tests/test_roots_seam.py).

**Fixtures:** a test that patched a module's `ROOT`/`FABRIC` now sets AGENT_FABRIC_OPERATOR to its fixture and restores it; fixture fabrics that copy a fixed file list must copy roots.py (the launcher loads it by path like git.py). Run the suite three ways: operator unset, set to a scratch copy, set to a nonexistent tree — only the last finds tests that still read live instance files.

**Why:** ADR-045 stage 2, behaviour-preserving. **How to apply:** any new reader of registries/catalog/policies/routing profiles/memory/ADRs/keys goes through roots; tests/test_roots_seam.py scans for direct joins and lists the coordinator-owned exemptions.

*Observed 2026-10-08 (python-dev)*
