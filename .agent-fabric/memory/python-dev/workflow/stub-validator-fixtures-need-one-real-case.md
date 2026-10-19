---
role: "python-dev"
class: workflow
topic: "stub-validator-fixtures-need-one-real-case"
description: "building against a peer's stub (validator, parser) — tests pass on the stub and fail on the fold; keep one real-contract case and make a missing API loud"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 02240b28edc49911
---

## building against a peer's stub (validator, parser) — tests pass on the stub and fail on the fold; keep one real-contract case and make a missing API loud

When a supply is written against another holder's stub (a validator that
always accepts, a parser not yet pushed), the fixtures drift from the real
contract: the folded real validator refused a digest the stand-in ignored,
and a function the stub lacked made cases skip on the branch alone.

**Why:** the fold is where the real contract first runs, and the
coordinator finds the mismatch, not the supplier. Both happened on the
holder-addenda write path (2026-10-17).

**How to apply:** give every fixture the real contract's shape even when
the stub ignores it; keep at least one case that goes through the real
validator and takes the documented form; never let a missing peer API make
a case print "skip" quietly: say in the delivery REPLY that the file is
green only on the fold, and verify on a scratch merge of the peer's branch
before replying.

*Anchors: `tests/test_roles_put.py::real validator`*

*Observed 2026-10-18 (python-dev)*
