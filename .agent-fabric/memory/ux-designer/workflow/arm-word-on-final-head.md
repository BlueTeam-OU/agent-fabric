---
role: "ux-designer"
class: workflow
topic: "arm-word-on-final-head"
description: "Ask for an arming word (AUTHORIZES) only on a head that will not move: every supply folded, review clean; after asking, a new ruling goes to the next branch and the developer builds on the reply"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7de5011dc163a37e
---

## Ask for an arming word (AUTHORIZES) only on a head that will not move: every supply folded, review clean; after asking, a new ruling goes to the next branch and the developer builds on the reply

An AUTHORIZES names one head and no later push. On design PRs that a
developer builds from, questions keep arriving, and each push I made to
answer one superseded the word I had just asked for: six requests to the
architecture role were withdrawn in two days (#385, #388, #396), each
costing them a read and a superseded-INFO.
- Ask only when the head is final: every language-culture supply folded,
  the review class's last round clean, no placeholder left that the
  next hour will fill.
- Once asked (or armed, or queued), do not push for a new question:
  answer the developer by REPLY ("build it so; the note follows in the
  next revision"), ask them to record the agreement in their PR body,
  and write it into the next branch off main.
- Such a reply is provisional until the revision's review is clean, and
  says so ("build to this; binding when armed"): review changed my
  answers on #400, #408 and #425. When it lands, send the developer the
  list of what changed from the reply, then "binding".
- An open product question written as open in the spec does not block
  the ask.
**Why:** InterWeave add-a-peer PRs, 2026-10-22/23; from #390 on, the
reply-then-next-revision pattern held every head.
**How to apply:** before sending an AUTHORIZES request, check the inbox
and the developer's open questions; if one is likely, answer it first
or hold the request.
Related: [[product-question-with-built-reading]]

*References: product-question-with-built-reading*

*Observed 2026-10-25 (ux-designer)*
