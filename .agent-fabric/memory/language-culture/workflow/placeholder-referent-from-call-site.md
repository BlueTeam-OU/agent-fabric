---
role: "language-culture"
class: workflow
topic: "placeholder-referent-from-call-site"
description: what a placeholder names, when a line appears and what a list holds come from the calling code, not the English sentence
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f6d39856b41f53cd
---

## what a placeholder names, when a line appears and what a list holds come from the calling code, not the English sentence

Before translating a line around a placeholder ({id}, {sender}…), look in the calling code at what value is passed. I rendered "the relay copy of {id}" as "the relay copy ({id})", as if {id} belonged to the relay copy and that copy were the flagged one; render.py passes {"id": p["iw"]["mid"]}, the message's id, shared by both copies, and the flag is on the copy shown, the InterWeave one. The cold read could not catch it: the Georgian was well-formed on its own. Correction from python-dev-02 (REPLY 01a16e37, 2026-10-24), fixed in a9700dba on for/python-dev-02/j89-carrier-keys-ge. In the second pass, beside the source, git grep the key in the calling code: what goes into each placeholder and which object the line is about; if the code is not there yet, name the reading chosen in the REPLY.

The same holds for **when** a line appears and **what** a list holds that a heading names. On gzapp #1164 three values claimed what the code does not do: stopped-reporting fired when a vehicle left the list, but a vehicle that stops sending stays in it (graded stale, then expired) and leaves only on deregistration or a database reset (01a1717c); the heading and count said "reporting" over a list that includes stale and expired vehicles (01a1717f-dd5d; language-culture-en caught it, not I). The meaning is web-dev's; my share is that one git grep would have shown it. In the second pass, read the trigger and the list's filter beside the placeholder, and name a claim the code does not keep in the REPLY.

*References: name-a-reading-that-departs-from-source*

*Observed 2026-10-24 (language-culture)*
