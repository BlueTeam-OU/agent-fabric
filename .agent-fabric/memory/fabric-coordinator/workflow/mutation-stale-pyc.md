---
role: "fabric-coordinator"
class: workflow
topic: "mutation-stale-pyc"
description: "a same-size sed mutation restored within the second leaves a stale __pycache__ that keeps the mutant running"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b66357a095677075
---

## a same-size sed mutation restored within the second leaves a stale __pycache__ that keeps the mutant running

A mutation control made with `cp f f.bak; sed -i 's/range(3)/range(1)/' f; ...; mv f.bak f` left
`tools/fabric/guards/__pycache__/secret_values.*.pyc` holding the MUTANT: the pyc is keyed by the
source's mtime (seconds) and size, and a same-size edit restored within the same second matches it.
The next test run (j424, 2026-10-30) failed for no reason in the code.

**Why:** a direct `python3 tests/...` import writes bytecode (the hooks set dont_write_bytecode, plain
imports do not).
**How to apply:** after a mutation control, delete the module's pyc (or run with
PYTHONDONTWRITEBYTECODE=1 throughout) before trusting the next result. Related: [[checks-need-a-control]].

*References: checks-need-a-control*

*Observed 2026-10-30 (fabric-coordinator)*
