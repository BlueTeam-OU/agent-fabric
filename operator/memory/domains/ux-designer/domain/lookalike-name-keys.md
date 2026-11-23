---
role: "ux-designer"
class: domain
topic: "lookalike-name-keys"
description: "A same-name (lookalike) check cannot be one fold-then-skeleton key: TS #39 prototypes are case-sensitive and NFKC both hides and reveals lookalikes; use several keys, any equal, and measure the rule over confusables.txt before sending…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5979fb67e6db974f
---

## A same-name (lookalike) check cannot be one fold-then-skeleton key: TS #39 prototypes are case-sensitive and NFKC both hides and reveals lookalikes; use several keys, any equal, and measure the rule over confusables.txt before sending even a provisional answer

A warning that two display names are "the same name" (a lookalike
impersonating a contact) fails in ways no single normalisation order
catches:
- Unicode TS #39 skeleton prototypes are case-sensitive, and some map to
  a capital after case folding has run (Lisu "ꓮ" -> "A", Cherokee "Ꭰ" ->
  "D"), so fold-then-skeleton misses them;
- skeleton-then-fold misses others (Greek capital Beta folds to beta,
  whose skeleton is "ss"; Lisu "ꓟ" -> "M" while small m's skeleton is
  "rn");
- NFKC turns some lookalikes into plain letters before the skeleton sees
  them (long s "ſ"), while other characters look Latin only after NFKC
  (circled or fullwidth letters and digits).
What held: three keys, each compared only with the same key of the other
name, any one equal = same name: case key (NFKC, spaces, fold, skeleton),
shape key (spaces, skeleton, fold, skeleton), compatibility shape key
(NFKC, then the shape key's steps). Errs toward a false warning ("Ian"
and "Lan"), which costs one comparison; a miss lets a lookalike pass.
**Why:** InterWeave contact-cards 5.4.1 (#438, 2026-10-25): my first
provisional fix, from two examples, was wrong within 15 minutes; a
sweep of confusables.txt found new misses twice more; the reviewer
reproduced the figures with ICU's skeleton.
**How to apply:** a rule that classifies a large table (confusables,
scripts, emoji) is run by a script over the whole table before any
answer, provisional included; the answer carries the miss count and the
script, and acceptance carries one fixture each key alone joins, so a
build missing a key fails.
Related: [[thresholds-as-formulas]]

*References: thresholds-as-formulas*

*Observed 2026-10-31 (ux-designer)*
