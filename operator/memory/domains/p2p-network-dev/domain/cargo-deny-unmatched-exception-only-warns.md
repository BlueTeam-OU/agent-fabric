---
role: "p2p-network-dev"
class: domain
topic: "cargo-deny-unmatched-exception-only-warns"
description: "cargo-deny passes green when a licence exception or allow entry matches nothing — a dropped [graph] target silently unjudges a platform's graph"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 400a5b7f115b2c65
---

## cargo-deny passes green when a licence exception or allow entry matches nothing — a dropped [graph] target silently unjudges a platform's graph

By default cargo-deny (0.20.2) reports a licence exception that matches no crate as
`warning[license-exception-not-encountered]`, and an unused allow entry as
`warning[license-not-encountered]`, and exits 0. So removing a target from
`[graph] targets` (or a feature dropping a crate) leaves that target's exceptions
matching nothing, and the target's graph stops being judged with every check green.
Note that `license-not-encountered` is not a substring of
`license-exception-not-encountered`, so a grep for the first misses the second.

Fix, in the gate rather than a self-test grep: under `[licenses]` set
`unused-license-exception = "deny"` and `unused-allowed-license = "deny"`; both are
accepted by 0.20.2 and turn the warnings into errors (exit 4 from cargo-deny).
A removal of the workspace member does NOT unjudge it under `all-features = true` when a
library crate's feature still reaches the dependency.

Found on InterWeave #314 (j91, 2026-10-19), round 1 F1; fixed at 034b04f5, with
tools/checks/test_check_dependencies.sh planting a dropped target and an unused licence.
Self-test lesson in the same fix: `printf "$out" | grep -q` under pipefail fails on a
large output (printf dies of SIGPIPE); use `grep -q … <<<"$out"`.

*Observed 2026-10-19 (p2p-network-dev)*
