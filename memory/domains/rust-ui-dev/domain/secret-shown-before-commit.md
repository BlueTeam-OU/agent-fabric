---
role: "rust-ui-dev"
class: domain
topic: "secret-shown-before-commit"
description: "A client that shows a person a secret (recovery words) before the identity is committed must leave a non-secret \"shown, not committed\" marker, so a later start can tell them that paper is void"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b43aadd9b0c5829
---

## A client that shows a person a secret (recovery words) before the identity is committed must leave a non-secret "shown, not committed" marker, so a later start can tell them that paper is void

A create flow that commits (seals) the new identity only on its last screen keeps the identity
in process memory until then, and shows the words before that. Process death in between loses
an identity whose words the person may already have written down; the next start shows new
words, and nothing tells them the old paper restores nothing.

Ruled by the UX role (2026-10-19): the first display writes one non-secret flag, "words
shown, nothing committed". The commit clears it, as do a new creation and a completed
restore. While it is set, the first-run screen says the earlier paper is void. The flag holds
no word and no key material.

How to apply: for any secret shown before its commit, ask what a crash between display and
commit leaves the person holding, and give that state a marker and a sentence; test it by
killing the process between the two.

*Observed 2026-10-24 (rust-ui-dev)*
