---
role: "language-culture"
class: workflow
topic: "sentence-about-the-document-is-a-claim"
description: "in a spec or template, a sentence about another part of it (a cross-reference, a self-description, a \"placeholder until\" note) is a claim; check it when you read, and again when you change the part it describes"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1cc6eb0f19aa79a9
---

## in a spec or template, a sentence about another part of it (a cross-reference, a self-description, a "placeholder until" note) is a claim; check it when you read, and again when you change the part it describes

A sentence that describes another part of the same document is a claim
about that part, not wording. It goes false without being touched.

- **A cross-reference.** "Naming the day in §5.2's words: Today, ..." was
  false, because §5.2 gives the time of day for today, not "Today"
  (F4). The same false reference was in a second place, "in §6's
  words", and I missed it in that round (F6, found one round later).
- **A self-description.** A spec said its strings table "gives each
  string's purpose and space, never its text". It became false when I
  wrote the text in, and needed a commit of its own.
- **A note in a template.** A release-page template said "every
  sentence below is a placeholder (en) until language-culture
  finalises it". My delivery made that false.

**Why:** a reviewer reads the sentence for its English and not for its
truth, and a writer who fills in the part it describes does not look
back at it.

**How to apply:** on a read, open every place that a sentence quotes
or names ("as §N says", "in §N's words", "the table below") and
compare. After writing into a document, search it for sentences about
the part you changed ("placeholder", "proposal", "pending", "no text",
the section's name) and correct them in the same delivery. Related:
[[key-value-true-in-every-state]], [[suggested-wording-in-target-style]].

*References: key-value-true-in-every-state, suggested-wording-in-target-style*

*Observed 2026-10-22 (language-culture)*
