---
role: "fabric-coordinator"
class: threads
topic: "coord-repo-plan-j290"
description: "agent-fabric-coord plan (j290, 2026-10-22): docs/split/agent-fabric-coord.md on PR #356; protocol/records/contract/conformance move, implementation stays; four owner questions open"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c45940bc5e7a62e
---

## agent-fabric-coord plan (j290, 2026-10-22): docs/split/agent-fabric-coord.md on PR #356; protocol/records/contract/conformance move, implementation stays; four owner questions open

The plan for GZCoord's own repository is `docs/split/agent-fabric-coord.md`, commit 670456ee
on PR #356 (branch develop-qzapp/user/feat/j350-…), written 2026-10-22 from origin/main a59d6fd9.

The cut: what a second, independent implementation needs moves (SPEC/MESSAGE-FORMAT/SEMANTICS/
CONFORMANCE, examples, adapter contract, human relay, history, ADR-032/033/030 re-issued in coord's
own series with stubs left in agent-fabric, a CONTRACT.md, a wire-only conformance corpus + a
stdlib grammar validator split out of gzmsg.py, the InterWeave carrier record). What makes the
fleet speak it stays (tools/fabric/gzcoord, relay unit, hooks, journal, intake), because it imports
identity/jobs/episodic and the control plane (ADR-029, `fabric:control`) rides the same relay.
agent-fabric pins a coord commit and CI runs the corpus at the pin.

Open with the owner: scope (recommended: implementation stays), history via subtree split,
visibility public, stubs vs rewriting the 22 citing files. Nothing moves before the answers;
the repository is created by the owner's hand ([[repo-transfer-owner-hand]]).
Related: [[gzcoord-not-on-interweave]].

j359 (the carrier record architect-cto-01 asked for, REQUEST 01a16532) was filed under project interweave by intake, but the record belongs in agent-fabric docs/adr as a commit on #356, not in an InterWeave worktree.

*References: gzcoord-not-on-interweave, repo-transfer-owner-hand*

*Observed 2026-10-22 (fabric-coordinator)*
