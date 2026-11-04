---
role: "python-dev"
class: solution
topic: "j72-launcher-exec-cuts"
description: "j72 PR #331 — where launch and new-agent execs come from, what was cut, review traps, waiting on owner's word to arm"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b16747cadd0f5fe6
---

## j72 PR #331 — where launch and new-agent execs come from, what was cut, review traps, waiting on owner's word to arm

PR #331 (branch develop-qzapp/python-dev-02/feat/j72-j300-cut-the-launcher-s-interpreter), head ce9a975a, reviewed clean, unarmed: touches launch.py + launcher/routing.py (security boundary), so 2 work commits arm only on the owner's word or a fabric-coordinator AUTHORIZES message.

Measured: `launch --print` is 5 Python starts (identity.py, routing.py session-effort, addenda.py, launch_prompt.py + launch.py), not 14. new-agent's cost is `bash -lc` login shells in provisioning/worker.py `as_login` (~25 execs of /etc/profile.d each; 739 across test_new_agent_cli).

**Why:** tests/test_provisioning_worker.py's fake git answers only `config --get`, so merging the two origin reads into `--get-regexp` broke the oracle. A review (F1) also rejected dropping the login shell for git reads: a read and the fetch/merge beside it must see one environment. Only `test`/`readlink` on a path go plain.

**How to apply:** re-review of a fix range needs `card_base` (first round's base) in the request; `post-review` records coverage on the head named in the dispatch header, so post each report before rendering the next brief. Wall times on this host (load 56-100) are not comparable; compare exec counts and user+sys CPU.

*Anchors: `tools/fabric/provisioning/worker.py::login_shell`, `tools/fabric/launcher/routing.py::session_effort`*

*Observed 2026-10-19 (python-dev)*
