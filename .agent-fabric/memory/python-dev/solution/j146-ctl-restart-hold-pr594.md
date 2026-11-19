---
role: "python-dev"
class: solution
topic: "j146-ctl-restart-hold-pr594"
description: "j146 / PR 594 — agentd's Leaver holds restart for open fabric-ctl socket sessions; state, design reasons, review recorded-by-whom trap, /tmp tmpfs trap"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ae89595e2bc03e2a
---

## j146 / PR 594 — agentd's Leaver holds restart for open fabric-ctl socket sessions; state, design reasons, review recorded-by-whom trap, /tmp tmpfs trap

MERGED 2026-11-14 (head cce405a3, 3 work + 2 fix + merges; armed on the owner's word, P3 F4-rest and F5 deferred via --defer "<reviewed head8>:F<n>" using the head each finding was raised on). Open: start_for_agentd hold annotation (control_link.py ~969) lacks `| None`; `assert not once` in hold_for_ctl; flaky test_a_peer_of_another_user_is_closed_unread (BrokenPipe on sendall).
PR #594 (branch develop-qzapp/python-dev-02/feat/j146-fabric-ctl-upgrade-fabric-loses-the, head d19d24c4, 2 work + 1 fix + 1 merge) —
the operator's own `upgrade fabric` restarted its agentd mid-command and closed the ctl socket, so on InterWeave alone later replies were lost.

Design: `control_link.Server(hold=...)` calls hold() when a request is accepted (after the `from` check) and release() in `finally`
or after HOLD_MAX_S (600 s, counted from the hold, logged); agentd's `hold_for_ctl` puts a token in `inflight` so the Leaver waits.
A session opened after `leave.pending` takes no hold (otherwise back-to-back presence/queue Legs keep old code forever).
Chosen over reconnect (b): replies reaching a restarted agentd before fabric-ctl reconnects have no watcher. ADR-029 rule 18 may want a sentence.

**Why:** carrier-alone control (W16) would lose every reply after the operator's restart.
**How to apply:** tests live in tests/test_control_agentd_dual.py (real agentd.main) and tests/test_control_dual.py (ctl on carrier alone).

Traps met:
- The suite's scratch is /tmp/af-t.* on a 2 GB tmpfs: 1.3 GB of my own stale dirs made two suites fail with ENOSPC; `df /tmp` first, remove only my own.
- A commit command containing $HOME is refused by the job guard; run lint with HOME separately.
- Auto-mode classifier refused `fabric-review save` of a report I had paraphrased by hand: a review report is the reviewer's verbatim text, never mine; save it from the hand-back unchanged.
- `fabric-review brief` repository field is a path, not owner/name.
- fabric-pr arm refuses open P3s until each is re-reviewed or `--defer`red; the defer names the head the finding was raised on (cf261933:F4), not the current head.
- `fabric-review next` needs a pinned range (sha..sha) and --head, and needs `fabric-review save 594 1 < report` first; the report file must be the subagent's text verbatim.

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::Server`, `tools/fabric/control/agentd.py::hold_for_ctl`*

*Observed 2026-11-14 (python-dev)*
