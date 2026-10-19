---
role: "flutter-dev"
class: workflow
topic: "resend-a-request-a-session-drained"
description: "A REQUEST whose recipient's session drained it and ended without replying is invisible to their next cursor — re-send it as the same ask naming the original MESSAGE-ID; after repeated silence send one consolidated list asking for the work…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e16b39609b39f888
---

## A REQUEST whose recipient's session drained it and ended without replying is invisible to their next cursor — re-send it as the same ask naming the original MESSAGE-ID; after repeated silence send one consolidated list asking for the work or a plain "not taking it".

A delivery is consumed when a session drains its inbox. If that session
ends before replying, the next session's cursor starts past it: the ask
is gone for the recipient, while the sender still waits. Seen both ways:
language-culture-ge re-sent a QUESTION to me ninety minutes on, "rather
than assuming it was ignored"; I re-sent two shift-key REQUESTs whose
recipients' sessions had drained and ended; and after five ka-GE items
went unanswered for four days I sent ONE list of all of them instead of
a fourth repeat.

**How to apply:**
- Re-send with the original id in the body ("Re-sending <id>, sent at
  <time> … the same ask, not a second one") so the recipient does not
  queue it twice.
- After a second silence, consolidate everything owed into one message
  and ask for either the deliverable or an explicit decline — silence
  is the only answer that leaves work unroutable.
- Before re-sending, check the branch and main for the delivery itself:
  the work may have landed without a reply.
- When a holder stays silent across sessions, ask fabric-coordinator
  whether the delivery reached its job list before chasing again
  (2026-10-15: the REQUEST was queued as a job; the session was stalled,
  not missing the message — the coordinator raised it with the owner and
  asked for no further chase).

*Anchors: `communication/gzcoord/protocol/SEMANTICS.md::REPLY-EXPECTED`*

*Observed 2026-10-18 (flutter-dev)*
