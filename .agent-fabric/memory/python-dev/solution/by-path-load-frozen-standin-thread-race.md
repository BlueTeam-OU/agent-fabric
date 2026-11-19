---
role: "python-dev"
class: solution
topic: "by-path-load-frozen-standin-thread-race"
description: "identity.py's _frozen sys.modules stand-in is not thread-safe; the daemon's identity+tokens sections race it (j230, tokens.days KeyError flake)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1a4b271c0aedf8a8
---

## identity.py's _frozen sys.modules stand-in is not thread-safe; the daemon's identity+tokens sections race it (j230, tokens.days KeyError flake)

runtime/identity.py `_frozen` puts a stand-in module in `sys.modules[cls.__module__]` for one
`dataclasses.dataclass` call and deletes it after. Tools load that file by path under one name
(`fabric_runtime_identity`: control/ops/util.state_dir and gzcoord/gzmsg._identity_module, plus
eight more loaders), and `ops.collect` runs the `identity` and `tokens` sections in two pool
threads. Thread A installs the stand-in, B sees it present (installs none), A deletes it, B's
dataclass reads `sys.modules.get(name)` = None: the tokens section answers
`{"status":"failed","error":"'NoneType' object has no attribute '__dict__'"}` and the test's
`["tokens"]["days"]` is a KeyError. Measured 8 of 400 fresh processes under `xargs -P 12`.

**Why:** a lock defined in identity.py is per loaded copy (each load has its own globals); the
shared object every copy imports is `dataclasses`, so the lock lives in its `__dict__` via
`setdefault`. The file is outside python-dev's `authority.json` paths, so the fix goes to
fabric-coordinator as a diff; the race test (tests/test_identity_context.py) forces the
interleaving with bounded waits and fails every run without the lock.

**How to apply:** a flake whose message is a failed section, not an assertion, is read from the
section's `error` string: spy the SECTIONS entry and loop fresh processes (a loop inside one
process never repeats a first-load race). A test that omits `state` in the ctx reads the
account's real ledger directory: give it a scratch one. See [[never-restore-a-mutation-with-git-checkout]].

*References: never-restore-a-mutation-with-git-checkout*

*Anchors: `runtime/identity.py::_frozen`, `tools/fabric/control/ops/util.py::state_dir`*

*Observed 2026-11-12 (python-dev)*
