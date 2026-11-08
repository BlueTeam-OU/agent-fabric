---
role: "fabric-coordinator"
class: workflow
topic: "phone-order-no-overlap-on-shared-peer"
description: a phone step that resets an identity leaves every other phone trusting the old one (retries look like interference); hold the lease for the whole case
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 996f48f81744deae
---

## a phone step that resets an identity leaves every other phone trusting the old one (retries look like interference); hold the lease for the whole case

2026-11-08, j648's phone order: step 1 (p2p-network-dev-01's release gate) uninstalled the InterWeave apps on the A40 at 12:12Z, which reset its identity.
The owner saw the Pixel "trying to send to the A40". This was not a test step. ux-designer-01's A17 ran against j228's host node only (REPLY 01a1bb26-2b41).
The Pixel's app kept retrying its own trusted contact, the A40 the owner added on 11-07 ("reconnect refused ... class=PeerBackoff"). I first blamed the
early 3b and was wrong; read the agent's own account before calling it interference. Also, the samsung-a40 lease read free while the A40 was mid-case.

**Why:** a lease guards a device, not a peer relationship. A step that wipes a phone's identity breaks every other step that trusts that phone,
on whatever device that other step runs.
**How to apply:** in a phone order, name for each step the phones it touches as a device and as a peer. A reorder that puts two steps side by side
must check both lists, and the coordinator answers every proposed reorder. Every step holds the lease of each phone it changes for the whole case,
waiting on the owner included.

*Anchors: `bin/fabric-lease`*

*Observed 2026-11-08 (fabric-coordinator)*
