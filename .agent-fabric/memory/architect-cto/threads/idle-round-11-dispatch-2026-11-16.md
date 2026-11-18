---
role: "architect-cto"
class: threads
topic: "idle-round-11-dispatch-2026-11-16"
description: "InterWeave idle round 11 (j738, 2026-11-16 ~17:00Z) — five REQUESTs to the Rust and network developers, what each asks, what I owe on their replies, and what was left unready"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d687996b08da3993
---

## InterWeave idle round 11 (j738, 2026-11-16 ~17:00Z) — five REQUESTs to the Rust and network developers, what each asks, what I owe on their replies, and what was left unready

j738, on fabric-coordinator's REQUEST 01a1e328 (the owner: idle Rust developers get InterWeave work).
Survey at InterWeave origin/main 3196cd731 (round 10's four jobs landed: #686, #687, #688; #684 queued).
Five REQUESTs, reply expected, branch name = acknowledgement:
- rust-ui-dev-01, 01a1e54b-2f19: hook that holds the app's call for add-a-peer acceptance 10's
  superseded cases (design/2026-10-22-add-a-peer.md l.1222, l.1617), then TM-45's unexercised
  failure-path lines (SECURITY-MATRIX l.132). I owe the design note's wording as a supply.
- rust-ui-dev-02, 01a1e54b-303d: after its j114 (A40 run for #669), a Gradle check of the Android
  permission allow-list against the merged manifest (plan l.7527); CI wiring is devex-tooling's.
- rust-services-dev-01, 01a1e54b-31ff: ANSWERED 01a1e54c-379c: fact 130 already in INSTALL.md on
  #684 (armed by the owner, queued at e027f72e6); step 8's interactive pty run is its j105, branch
  feat/j105-step8-interactive-pty after #684 merges.
- rust-services-dev-02, 01a1e54b-32f0: SPIKE-001 S38 (cause and rate of a --channels session with
  no channel, fact 130, 2.1.322 and 2.1.325, channel_enable), then S37's Not-established list.
  I owe plan s19 + SPIKES.md + architecture/plugin propagation as a supply.
- p2p-network-dev-01, 01a1e54b-3478: CONNECTIVITY.md s14 Not-proved (a) far end returns and dials,
  (b) returns on another address, (c) idle past 180 s, in two_hosts.rs. I owe the s14 paragraph.
Not sent: p2p-network-dev-02 (j110 phones). Final REPLY to fabric-coordinator: 01a1e54c-7588.
Not ready, before the owner: Stage 22, human store export, and a Stay reachable control on Android:
the app has NO such switch (p2p-network-dev-02 INFO 01a1e54b-4da8, verified: design/2026-11-05-
unlock-policy-pending.md l.503 lists the control as not built; every device run wrote
availability-overlay.json by hand). My earlier asks of the owner to "turn Stay reachable on" named a
switch that does not exist; p2p-network-dev-02 asked the owner for the word to write the overlay.
Same session: A40 released to rust-ui-dev-02 on my word (REPLY 01a1e546-d4f9; it may uninstall
p2p-network-dev-02's debug pair with data); ux-designer-01 told the #669 run has not happened yet
(REPLY 01a1e546-d649), record goes to it from rust-ui-dev-02.
Remaining ready pool after this round (from the survey): S32(a) compaction cells on 2.1.325;
s14's learned-address cases and the 30 s redial host cost (p2p). Nothing else.
17:00Z ANSWERS: rust-ui-dev-01 took it as j284 (branch feat/j284-interweave-next-job-the-hold-the);
rust-ui-dev-02 as j116 behind j114 (feat/j116-android-permission-allow-list; j114's two A40 cases
running since 16:54Z); rust-services-dev-02 as j78 (feat/j78-spike-001-s38-channel-less-session).
p2p-network-dev-01 had not answered when the session moved on. j739 (#687 arm word) is stale:
#687 (5 work, 2 fix, 3 merge) merged 3196cd731 on my word 01a1e35b; close it in its session.

*Observed 2026-11-16 (architect-cto)*
