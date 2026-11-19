---
role: "python-dev"
class: solution
topic: "j132-relay-probe-bound-delivered"
description: "j132 — watch-on-stop relay probe bounded by a joined daemon thread; branch/head, test recipe, branch-name trap"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7ece292382580858
---

## j132 — watch-on-stop relay probe bounded by a joined daemon thread; branch/head, test recipe, branch-name trap

j132 (#520 F3/F4): `relay_answers` in runtime/claude-code/hooks/watch-on-stop.py runs urlopen in a daemon thread joined for RELAY_PROBE_S (urlopen's timeout is per socket op, so DNS/addresses/a dripped status line exceed it); `decide()` checks recently_blocked before the probe. Delivered as branch develop-qzapp/python-dev-02/for/user/j132-relay-probe-bound, head bb1bb4d9, reply 01a1c117 sent.

**Why:** the test needs a drip server (one byte per 0.3 s, no newline) — a closed or silent port trips the per-op timeout anyway and proves nothing. Mutations: join timeout x8 and recently_blocked moved back are both red.

**How to apply:** a hook under runtime/claude-code/hooks is a supply path: commit only on a `for/user/` branch; the hook refused the `feat/` branch name the job created, so rename (git switch -c) before committing.

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::relay_answers`*

*Observed 2026-11-09 (python-dev)*
