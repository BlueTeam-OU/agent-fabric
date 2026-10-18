---
role: "fabric-coordinator"
class: workflow
topic: "in-reply-to-read-not-typed"
description: "Before sending a REPLY, copy IN-REPLY-TO from the delivery's MESSAGE-ID line (gzcoord-inbox --replay <seq>); never type or recall it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f2201a5e7014a79b
---

## Before sending a REPLY, copy IN-REPLY-TO from the delivery's MESSAGE-ID line (gzcoord-inbox --replay <seq>); never type or recall it

2026-10-16: twice in one hour I sent a REPLY whose IN-REPLY-TO I had typed instead of read
(to legal-expert-ee-eu, to python-dev-02); both named ids that do not exist, and each needed a
correction message. I had read only the delivery's SUBJECT and body, never its MESSAGE-ID line.

**Why:** since #274/#277, IN-REPLY-TO is what settles an owed answer and a reply: artifact; a
wrong id leaves the sender's switch refusing and costs a correction broadcast to that agent.
**How to apply:** when listing a delivery, grep its MESSAGE-ID with the SUBJECT; a REPLY's
IN-REPLY-TO is pasted from that line in the same turn. Related: [[verify-sends-in-journal]].

*References: verify-sends-in-journal*

*Anchors: `communication/gzcoord/protocol/MESSAGE-FORMAT.md::IN-REPLY-TO`*

*Observed 2026-10-16 (fabric-coordinator)*
