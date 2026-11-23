---
role: "rust-ui-dev"
class: domain
topic: "forced-crash-no-core"
description: "A test that forces a crash (abort) of a process holding a key or content writes a core the host's collector keeps; make it non-dumpable first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7afca2339ab285af
---

## A test that forces a crash (abort) of a process holding a key or content writes a core the host's collector keeps; make it non-dumpable first

`std::process::abort()` to simulate a crash dumps core. On a host whose
`core_pattern` pipes to systemd-coredump, the core lands in
`/var/lib/systemd/coredump/` owned by root: the test's account cannot
delete it, and it holds the process's memory -- the store key, the test
content. SPIKE-011's crash rows left 15 such cores (InterWeave j130,
2026-10-21) before the harness was fixed; `ulimit -c 0` does not stop a
piped core_pattern reliably.

Rule: a forced crash first calls `prctl(PR_SET_DUMPABLE, 0)`, then
aborts: the kernel writes no core at all (verified: coredumpctl count
unchanged). Check `coredumpctl list` after any test that aborts; cores
already there need the owner's `sudo rm`. Related:
[[sqlite-deletion-residue]].

*References: sqlite-deletion-residue*

*Observed 2026-10-21 (rust-ui-dev)*
