---
role: "fabric-coordinator"
class: workflow
topic: "threat-model-before-boundary-request"
description: "A REQUEST for code at a security boundary carries its threat model and refusal tests up front, and asks for the narrowest input — #236's settings-put took 16 review-fix commits / 26 reviews for 2 work commits"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2fc6242a6e1f3044
---

## A REQUEST for code at a security boundary carries its threat model and refusal tests up front, and asks for the narrowest input — #236's settings-put took 16 review-fix commits / 26 reviews for 2 work commits

#236 (python-dev-02, 2026-10-13): my REQUEST for `fabric-secrets store settings-put --from <dir>`
gave the shape ("copies the tree under <dir> to settings/, refusing .., links and anything outside")
and acceptance, not a threat model. Every review round then found the next case — a link in the
source, in an ancestor, in settings/ itself; interrupts before and after the commit; leftover dirs;
staged bytes ≠ validated bytes — 16 review-fix commits, 26 posted reviews, against 2 work commits.
The owner: "16 fix for 2 work ... that's a bad record".

**Why:** a boundary writer built to the happy path is hardened case by case by the most expensive
loop we have (two engines per round); the cases were knowable up front.
**How to apply:** for any request touching secrets, stores, keys or files from untrusted input:
(1) write the threat model in the REQUEST — what is hostile (paths, links, special files, races,
interrupts, partial writes) and what must be refused — with each case named in ACCEPTANCE as a test;
(2) ask for the narrowest input (named files, not "a tree"); (3) new work that lands on a PR opened
for something else goes to its own PR and is Kind: work.

*Observed 2026-10-13 (fabric-coordinator)*
