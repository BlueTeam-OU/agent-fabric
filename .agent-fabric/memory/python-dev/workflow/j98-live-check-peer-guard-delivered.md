---
role: "python-dev"
class: workflow
topic: "j98-live-check-peer-guard-delivered"
description: "j98-j100 live_interweave_two_accounts.py J92_PEER fixes — one shared peer check, usage text, for/ branch head, fabric-jobs done needs an artifact"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00a5367cf9f1ba5b
---

## j98-j100 live_interweave_two_accounts.py J92_PEER fixes — one shared peer check, usage text, for/ branch head, fabric-jobs done needs an artifact

j98/j99/j100 were three review-driven commits on the for/ branch
`develop-qzapp/python-dev-02/for/user/j401-rule-13-peer` (head 3bc8e0a7):
dead `doc` read dropped (F841), `peer_refusal()` called first by check,
serve, exchange and portcheck (not stop), J92_* inputs in the usage print.

**Why:** a rule found on one phase (F9) was about every phase; the docstring
also said "every phase checks it" while stop rightly does not (F10).
**How to apply:** when a review names an input a phase needs, add one shared
check every phase calls plus the usage line, and say in prose which phases
are exempt.

`fabric-jobs done jX` with no artifact leaves the job unable to be left:
`fabric-jobs switch` then refuses ("done needs evidence"). Run
`fabric-jobs deliver jX <sha|branch|reply:ID>` first, or `done --no-artifact`.
A fleet hold lifted by DECISION means delivered-but-queued jobs are closed,
not started.

*Anchors: `tests/live_interweave_two_accounts.py::peer_refusal`*

*Observed 2026-10-30 (python-dev)*
