---
role: "fabric-coordinator"
class: workflow
topic: "phone-uninstall-classifier-varies"
description: "auto mode refused adb uninstall in one session and allowed it in another; an owner's word reaches no classifier; policy entry on #510 (654eb3b8)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d3807dad3b944708
---

## auto mode refused adb uninstall in one session and allowed it in another; an owner's word reaches no classifier; policy entry on #510 (654eb3b8)

2026-11-08, phone order step 2: rust-ui-dev-01's auto-mode classifier refused `adb uninstall org.interweave.human` as
"Irreversible Deletion". rust-ui-dev-02's classifier allowed the same command on the A40 twelve minutes later.
The owner's word, given in another session ("agents may uninstall and clear data on both phones"), reached neither check.

**Why:** the classifier judges each session from its own transcript. A word the owner gave elsewhere is not in that transcript,
so two sessions can rule differently on the same command.
**How to apply:** an owner's standing permission that agents act on goes into policies/auto-mode.json as a bounded allow
entry with a test (here: the org.interweave. packages, the two phones, under the lease; agent-fabric #510, 654eb3b8). It
reaches a session after merge, `fabric-ctl all upgrade fabric` and a relaunch. Say that wait when a step depends on it.
Related: [[phones-uninstall-word-2026-11-08]], [[agent-auto-mode-refusals]].

*References: agent-auto-mode-refusals, phones-uninstall-word-2026-11-08*

*Anchors: `policies/auto-mode.json::adb uninstall`*

*Observed 2026-11-08 (fabric-coordinator)*
