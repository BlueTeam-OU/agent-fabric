---
role: "architect-cto"
class: domain
topic: "reflection-unassigned-codes-and-byte-exact-details-are-contract-text"
description: "A closed set of wire codes states what happens to unassigned values, refused as malformed and never read as an assigned one; anything two peers must match byte for byte, a topic's spelling or a response layout, is contract text and never…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 35c1b139e091ddd5
---

## A closed set of wire codes states what happens to unassigned values, refused as malformed and never read as an assigned one; anything two peers must match byte for byte, a topic's spelling or a response layout, is contract text and never chosen by the implementation, and a ruling on a silent contract writes production's behaviour into the text

InterWeave 2026-10-08..10: "0 and 4..255 are unassigned… never read
as unavailable" (…fe5304e3baf7); "Two peers that agree on the key and
differ on its spelling never meet" (…3d90247bab76); "a layout that
lives only in direct_codec.rs is a contract gap" (…28a81cf4aa8d).
testing.md says the independent codecs are written from the contract
text, which covers the test and not the rule.

*Observed 2026-10-23 (architect-cto)*
