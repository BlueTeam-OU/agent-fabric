---
role: "ux-designer"
class: domain
topic: "picker-whole-word-prefixes"
description: A narrowing word picker (type letters, pick from matches) must offer a typed whole word that is also a prefix of others, or such words can never be entered
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bb622880411ccd9e
---

## A narrowing word picker (type letters, pick from matches) must offer a typed whole word that is also a prefix of others, or such words can never be entered

When a picker hides suggestions until few enough words match, a word
that is complete AND a prefix of many others never reaches the
suggestion row: every further letter leaves it behind. In the BIP-39
English list, act, can, car, cat, man and win each prefix five or more
words (car: car, carbon, card, cargo, carpet, carry, cart), so a
"show chips at four or fewer" rule made them unenterable (~6.8 % of
24-word phrases).

**Why:** InterWeave #303's blind review, round 1 (2026-10-19), P1 on
design/2026-10-19-android-identity.md §4; confirmed by the review
class's own count over bip39-2.2.2's wordlist.

**How to apply:** for any narrowing picker over a closed list, compute
(do not assume) the worst case over the list — every entry that is a
prefix of others — and always show an exact match as its own choice;
add an acceptance item that enters one such entry.

*Observed 2026-10-19 (ux-designer)*
