---
role: "language-culture"
class: domain
topic: "colon-list-in-sign-in-reads-as-required"
description: "In sign-in copy, \"Sign in to see X: A and B\" reads as \"you must give A and B\"; use a second sentence"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 6537463af0fc7f5f
---

## In sign-in copy, "Sign in to see X: A and B" reads as "you must give A and B"; use a second sentence

In a sign-in prompt, a colon followed by data items ("Sign in to see your profile: your name and email address.") was read by a second-language cold reader as the items they must give to sign in, not the items they will see. Two sentences took away that reading: "Sign in to see your profile. It shows your name and email address." (gzapp premium.view-profile.body, commit 3eff13265, 2026-11-14, j320.)
**Why:** next to a Sign in button, a list of personal data reads as a form's requirements.
**How to apply:** in any sign-in or consent copy, say what is shown in its own sentence, with a verb ("It shows ..."). When a sibling locale uses the same colon form, tell its holder. See [[cold-read-mark-the-changed-words]].

*References: cold-read-mark-the-changed-words*

*Observed 2026-11-14 (language-culture)*
