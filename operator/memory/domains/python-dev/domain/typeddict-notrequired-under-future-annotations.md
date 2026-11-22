---
role: "python-dev"
class: domain
topic: "typeddict-notrequired-under-future-annotations"
description: "typing a dict-convention record in this fabric — NotRequired is silently required under `from __future__ import annotations`; hold each type to real values by test"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 41e2d84915aaa886
  - b025042b7fe1cf39
---

## typing a dict-convention record in this fabric — NotRequired is silently required under `from __future__ import annotations`; hold each type to real values by test

Under `from __future__ import annotations`, which nearly every fabric module
has, a TypedDict's annotations are strings. TypedDict then does not recognize
`NotRequired[...]` inside them: `__required_keys__` lists every key, and
`__optional_keys__` is empty. Nothing errors. The type just claims every key
is always there. Found by the structural test of j28's first commit
(gzcoord/gzmsg.py Whoami and RoleRecord, 2026-10-06).

Use a required base class and a `total=False` subclass for the optional
keys (`class _Keys(TypedDict): ...` / `class Rec(_Keys, total=False): ...`).
That works whether annotations are strings or not.

**Why:** the fabric's typing is option (B), with no checker (agreed with the
coordinator, 01a108cd). An annotation nothing checks drifts from the code,
and this one was wrong from the start.
**How to apply:** for every TypedDict, write a structural test that builds
the REAL value. Use the CLI or the function on scratch state, every outcome
or shape. Assert that `__required_keys__` <= keys <= required | optional.
Mutate both ways: a producer that adds a key, and a type that drops one. The
control plane's envelope kinds do the same through their keys exported as data
(ENVELOPE_KEYS in tools/fabric/control/protocol.py; the Node JSDoc typedef it first covered is gone). See
[[splitting-a-closure-heavy-main]].

*References: splitting-a-closure-heavy-main*

*Observed 2026-10-11 (python-dev)*
