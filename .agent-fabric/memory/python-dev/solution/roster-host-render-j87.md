---
role: "python-dev"
class: solution
topic: "roster-host-render-j87"
description: "j87 (#400) roster rows with a host - optional signed field, wildcard listener, review traps (scope-id YAML injection, roots seam, post-review denial)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1d0223f1023bab9d
---

## j87 (#400) roster rows with a host - optional signed field, wildcard listener, review traps (scope-id YAML injection, roots seam, post-review denial)

#400 (merged d104c86e, 2026-10-27): roster.py rows may carry `host`; `canonical_row` signs it only when present (old rows stay valid); registry attached by `with_hosts` only when a row names a host. Render: hosted account listens on 0.0.0.0/:: (architect-cto R7: a literal-address listener loses network-change detection), same-host peers dial 127.0.0.1, other-host peers dial the host's `interweave_address`.

**Why / traps:** `ipaddress.ip_address` accepts IPv6 scope ids (`fe80::1%<any text>`), so a registry value reached config.yaml as YAML injection (P1): refuse scope_id/unspecified/multicast/reserved/mapped and emit lists with json.dumps. A hand-joined `hosts/registry.json` fails tests/test_roots_seam.py: use `roots.hosts_registry()`. The owner may supply schema changes onto your branch mid-PR, moving the head: re-render the review brief for the new head. Put a review-brief dispatch in the Agent prompt in full (a placeholder gives an empty review). `fabric-pr post-review` was once denied by the auto-mode classifier; the owner ran a script in the scratchpad (`! path`), never a `<placeholder>` command.

**How to apply:** still open as P3s: host_address accepts IPv4 loopback/link-local; IPv6 host same-host dial over /ip4/127.0.0.1 is unproven (V6ONLY).

*Anchors: `tools/fabric/gzcoord/carrier/roster.py::host_address`*

*Observed 2026-10-27 (python-dev)*
