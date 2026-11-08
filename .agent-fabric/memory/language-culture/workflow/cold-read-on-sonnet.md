---
role: "language-culture"
class: workflow
topic: "cold-read-on-sonnet"
description: "how a cold read is dispatched — read-only Explore on model sonnet, never opus; report a miss with its example"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04271d8ccbae9033
  - 855ca55c3101eb26
  - 9fcb059d519abb75
---

## how a cold read is dispatched — read-only Explore on model sonnet, never opus; report a miss with its example

A cold read is a fresh reader with no context who judges whether a finished text reads naturally. Dispatch it as a read-only `Explore` agent on model `sonnet`, not `opus`. The dispatch guard does not ask the owner for sonnet, and it costs about a fifth as much. The `locale-worker` (on the logins that have one) stays on opus, as agent-fabric ADR-027 designs it. This was a fabric-coordinator DECISION with the owner's word, 2026-10-10.

**Why:** every opus Explore asked the owner for approval, and the accounts were near their weekly allowance. A cold read tests comprehension and naturalness, and sonnet does this well.

**How to apply:** give the cold reader only the text, its audience and the rules it must hold. Name the model in the Supplier-Review trailer ("cold read by a fresh dispatch (sonnet) ..."). If a sonnet cold read misses something that a stronger read would have caught, send the example to fabric-coordinator. The rule changes on evidence.

**What the reader needs besides the text** (reflection W43): cold reads
given only the composed text had most findings withdrawn: 12 of 12
(01a15f49), 13 of 13 (01a1628c), 13 of 14 (01a162a2), 10 of 11
(01a15f40). Most asked for a term that a text on the same screen
defines, or judged final values that the new key only quotes (status
texts, error sentences). Give the reader the texts shown beside the
new one on that screen, and mark the quoted values as final and out of
scope, so its findings fall on the new words.

**The reader reads my wording, not only the author's** (reflection
W44): six of its catches that week were in my own first drafts. Three
were a new "it" or "they" with two referents, in the sentence I wrote
to remove one (01a17211, 01a173bd, 01a173c6). One was a string that
did not say what the photo was included in (01a17b7d). Two were lines
that contradicted another section of the same page. The reader found
them only because it was given the page around the line (01a18bd0,
01a18bd3). So dispatch the cold read on the replacement text in its
place, after the edits. Before that, read each replacement sentence
for its own pronouns, since a fix for one pronoun often adds another.

*Observed 2026-10-31 (language-culture)*
