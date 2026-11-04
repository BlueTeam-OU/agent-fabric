---
role: "language-culture"
class: domain
topic: "uncontrolled-value-away-from-punctuation"
description: "a filled value whose characters the text does not control (a path, a typed name, a label ending in \"…\") goes where no sentence punctuation or list joiner touches it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91eef069c6ef43c0
---

## a filled value whose characters the text does not control (a path, a typed name, a label ending in "…") goes where no sentence punctuation or list joiner touches it

Some values can contain the characters that the sentence around them
uses. The reader then cannot tell where the value ends. Three cases in
InterWeave, W43:
- A folder `{path}` can contain commas and spaces. Between commas in the
  middle of a sentence, it merges with the words around it. It went
  last, with no full stop. Then ux-designer-01 made it a key of its own,
  on its own line (`KeyDirUnsafePath`, "Folder location: {path}").
- Contact names that a person typed can contain "and" or a comma. A
  list joined as "Ana, Ben and Chloe" can then read as more contacts
  than there are. The row now shows one name per line.
- A control label that ends in "…" ("Open an image…") at the end of a
  sentence reads as a sentence that trails off. A full stop after it
  gives "image….". The label stays in the middle of the sentence.

**Why:** a template is checked with tidy example values. The value that
breaks it is one the writer did not choose.

**How to apply:** for each placeholder, ask what characters its real
values can hold. If they can hold the sentence's own punctuation or
joiners, put the value last or on its own line (its own key). Do not
join such values into a list. Say this to the caller as a layout
question when it needs a new key.

Related: [[key-value-true-in-every-state]]

*References: key-value-true-in-every-state*

*Observed 2026-10-25 (language-culture)*
