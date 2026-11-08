---
role: "fabric-coordinator"
class: workflow
topic: "hygiene-pattern-span-is-substituted"
description: "a policies/hygiene.json pattern's whole match is what the drain replaces with refer_as: match only the withheld token (context in lookbehinds), and test the substitution, not only the hit"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2d2044f28ac15c2d
---

## a policies/hygiene.json pattern's whole match is what the drain replaces with refer_as: match only the withheld token (context in lookbehinds), and test the substitution, not only the hit

j533, #497 round 1 F3 (2026-11-06): my four GitHub-owner patterns matched `github.com/<owner>/` and
`--repo <owner>/x` whole, with refer_as "an upstream repository"; lint passed and the tests passed, but
`core.hygiene_substitute` (the drain) replaces the whole match, so a slice would have read
`https://an upstream repositoryovergraph`. Fixed in 308d9d54: each pattern matches the owner alone
(fixed-width lookbehinds OR'ed, `(?=/…)` lookaheads), refer_as `<owner>`, and the suite runs
hygiene_substitute on every form. The same round (F1): a pattern keyed on `-R`, `repos/` or a
"repo" label matched plain paths (`cp -R a/b`); a form a path looks like is a stated gap, not a pattern.

**Why:** a hygiene entry has two readers, lint (refuses) and the drain (rewrites); a test of the first proves nothing about the second.
**How to apply:** for any new hygiene entry, add a case that the substituted text reads right, and run lint over the sibling corpora (ports like `github.com:443` and placeholders like `--repo o/n` showed up only there). See [[hygiene-name-covers-handles]].

*References: hygiene-name-covers-handles*

*Anchors: `tools/fabric/assembler/core.py::def hygiene_substitute`, `tests/test_hygiene_github_owner.py`*

*Observed 2026-11-06 (fabric-coordinator)*
