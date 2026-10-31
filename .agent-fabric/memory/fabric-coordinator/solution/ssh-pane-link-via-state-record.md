---
role: "fabric-coordinator"
class: solution
topic: "ssh-pane-link-via-state-record"
description: "How the Fleet Deck links an ssh pane to its session — through the State record, never by reading the account's state dir"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cfe4aab0fd46b939
---

## How the Fleet Deck links an ssh pane to its session — through the State record, never by reading the account's state dir

enter-ssh (c3e476c2) writes `ssh-clients/<pid>` = sshd's SSH_CLIENT under the
account's state dir, mode 700. The deck runs as the operator login and cannot read it, so the
link travels on the control plane: agentd's sessions.py walks each live
session's pid up to an ancestor with a record and adds an optional per-session
`"ssh_client": {"addr", "port"}` to the State that `fabric-ctl all states --json`
streams. The deck matches that against its own ssh process's local socket
(/proc/<pid>/fd → inode → /proc/<pid>/net/tcp{,6}). Dispatched 2026-10-15:
python-dev-04 REQUEST 01a13e86 (agentd), rust-ui-dev-02 REQUEST 01a13e87 (deck,
merges after the agentd PR). Then tab-states.md drops the RUNNING-not-ELSEWHERE caveat (j83).
Related: [[data-and-reader-together]].

*References: data-and-reader-together*

*Anchors: `runtime/provisioning/moveto/enter-ssh::record_client`, `tools/fabric/control/sessions.py::read_sessions`*

*Observed 2026-10-15 (fabric-coordinator)*
