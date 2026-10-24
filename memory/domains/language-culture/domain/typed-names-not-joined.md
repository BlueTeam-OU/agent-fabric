---
role: "language-culture"
class: domain
topic: "typed-names-not-joined"
description: "names a person types (contact names) are never joined into one list string; a name holding \"and\" or a comma reads as more people"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d08ff6789271cc4e
---

## names a person types (contact names) are never joined into one list string; a name holding "and" or a comma reads as more people

Names that a person types themselves, such as InterWeave contact names, can contain "and" or a comma: "Mum and Dad", "Smith, John". Joined by a list pattern, they read as more people than there are: "Smith, John and Ana" reads as three. No wording can prevent this.

On 2026-10-23, ux-designer-01 dropped the joined `PeerContactNames` from add-a-peer s5.2 for this reason. A Peers row now shows one name per line (83f52cfe on #388, REPLY 01a16656-6e8f). My list pattern, e1392ddf, was not folded.

**Why:** a list pattern assumes that each item is one unit. Text that people type breaks that assumption, and a translation cannot fix it.

**How to apply:** when a request asks for user-typed names to be joined, raise the layout first (one line or one chip per name). Word a joined pattern only for items the app itself names. Also note that CLDR's en list pattern puts a comma before "and", but this copy has none ("PIN, pattern or password"). So a joined list needs either explicit templates or acceptance of the formatter's comma. Related: [[interweave-copy-conventions]].

*References: interweave-copy-conventions*

*Observed 2026-10-23 (language-culture)*
