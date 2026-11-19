---
role: "python-dev"
class: solution
topic: "j129-w2-b-transport-pr528"
description: "j129 W2-B: PR 528 message transport package; seams kept for the old suites, checker/policy handoff, test and mutation traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - af688b665f1462d0
---

## j129 W2-B: PR 528 message transport package; seams kept for the old suites, checker/policy handoff, test and mutation traps

#528 armed 2026-11-09 at ff99b752 (10 work, 1 fix; count rule min 1). Policy content went in the REPLY (hook refuses policies/ on for/ branches); coordinator wires transport_calls and the enforced mark. j131 (HELLO arrival line, hook is `TransportMux.on_arrival`) and j132 (#520 probe) wait for the merge.

**Why:** old suites (protocol, port, carrier adapters) call `wait_loop(fetch_page, ack, ..., iw=, ledger=)` and `inbox.api/RelayError/ensure_relay` directly, so the move kept those seams and re-exports; the mux supplies the callables.

**How to apply:**
- A method named `history()` on any object trips the i18n suite (every `history(` call must pass `t`); the transport's read is `newest()`.
- A lint rule bans the carrier's name in generic files: use CARRIER_NAME / "second carrier" in tools/ prose.
- Mutation pass: a survivor means a missing test; `test_gzcoord_carrier_adapters` hangs (not fails) under some dedup mutations, so the harness treats a timeout as killed; short TMPDIR (AF_UNIX path) and commit/clone in separate Bash calls (job-copy hook trips on a `cd` elsewhere plus `git commit`).
- Carried P3s: checker misses a 2-arg relay call through a module name; dedup assumes one mirror; send.py imports the adapter at start.

*Anchors: `tools/fabric/gzcoord/transport/mux.py::TransportMux`, `tools/fabric/transport_calls.py::scan`*

*Observed 2026-11-09 (python-dev)*
