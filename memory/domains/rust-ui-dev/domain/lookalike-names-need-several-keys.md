---
role: "rust-ui-dev"
class: domain
topic: "lookalike-names-need-several-keys"
description: "Comparing person-chosen names for 'same name' against lookalike spoofing: one normalised key misses pairs; use several keys (case, shape, compatibility shape) OR-compared, proved by a confusables.txt sweep"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0a7d6114d3d3f913
---

## Comparing person-chosen names for 'same name' against lookalike spoofing: one normalised key misses pairs; use several keys (case, shape, compatibility shape) OR-compared, proved by a confusables.txt sweep

A "same name" warning (a contact card claiming a name already held by another key) is a
spoofing defence, so it must err toward warning. No single normalisation string does it,
because Unicode TS #39's skeleton, case folding and NFKC do not commute:
- fold before skeleton misses lookalikes whose confusable prototype is uppercase
  (Lisu U+A4EE -> "A", Cherokee U+13A0 -> "D", Lisu U+A4DF -> "M"; a small m's skeleton is "rn");
- fold before skeleton also turns Greek capital Beta into beta, whose skeleton is "ss";
- NFKC before skeleton erases long s (U+017F) into s, so "Alſie" misses "Alfie";
- dropping NFKC loses compatibility joins (fullwidth digit zero vs "O", circled capitals).

What held after five review rounds (InterWeave design 5.4.1, 2026-10-25), three keys, two names
the same when ANY one key matches its counterpart:
- case key: NFKC, whitespace collapsed, full case fold, skeleton;
- shape key: whitespace, skeleton, fold, skeleton;
- compatibility shape key: NFKC, then the shape key's steps.
The relation is not transitive: compare pairs, never group by one key or use one indexed equality.

**How to apply:** for any lookalike comparison, measure candidate keys by a script sweeping
confusables.txt (count joined and missed pairs) rather than reasoning about the order of steps;
keep, as unit fixtures, one pair joined by each key alone ("Ian"/"ian" case only, "Alſie"/"Alfie"
shape only, "J０hn"/"John" compatibility only) plus controls that must not join ("Mia"/"Max",
"Hanna Rossi"/"Anna Rossi"), and a title test that asserts each title holds its distinguishing id,
not merely that titles differ (a lookalike pair passes assert_ne vacuously).

*Observed 2026-10-31 (rust-ui-dev)*
