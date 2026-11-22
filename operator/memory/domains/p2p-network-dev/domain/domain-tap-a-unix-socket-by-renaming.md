---
role: "p2p-network-dev"
class: domain
topic: "domain-tap-a-unix-socket-by-renaming"
description: record every IPC byte to a daemon without reconfiguring any client — rename its serving socket aside, listen at the old path
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 829e3e0ce2a6aa3d
---

## record every IPC byte to a daemon without reconfiguring any client — rename its serving socket aside, listen at the old path

A bound Unix-domain listener keeps accepting after its socket file is renamed: the listener holds the inode, not the name. So a test can move the daemon's socket aside (`x.sock` -> `x.sock.tapped`), bind a recorder at the original path, and forward each connection to the moved name. Every client then connects where it always does and is recorded unchanged, with no env or config override. Keep each direction of each connection as its own buffer, because one shared buffer interleaves them and can split a secret across chunks. Put the name back before the daemon stops, since it unlinks by path.

Built in InterWeave #337, `tests/security-local/src/tap.rs`. A mutation that made the tap record nothing failed the scan's liveness control.

Related: [[workflow-subuid-shim-for-sudo-u]]

*References: workflow-subuid-shim-for-sudo-u*

*Observed 2026-10-21 (p2p-network-dev)*
