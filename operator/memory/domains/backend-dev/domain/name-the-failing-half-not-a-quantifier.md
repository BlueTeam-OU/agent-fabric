---
role: "backend-dev"
class: domain
topic: "name-the-failing-half-not-a-quantifier"
description: "Writing or reviewing prose, a log line or an error message about a guard over two or more conditions — name which condition failed; a quantified sentence (\"both\", \"and\", \"no X and Y\") inverts under negation"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - c94be26fab752074
---

## Writing or reviewing prose, a log line or an error message about a guard over two or more conditions — name which condition failed; a quantified sentence ("both", "and", "no X and Y") inverts under negation

A sentence that describes a guard over two conditions with a quantifier is
usually wrong in the case it exists for. The guard is
`[ -n "$a" ] && [ -n "$b" ]`, so it fails when EITHER half fails. "When both
can be read" is true as written, but the case it warns about is its negation,
and a reader takes that as "when neither can be read", which is narrower than
the code. "No single-line A and B" reads distributively as "no A and no B",
yet it prints when only one of them is missing. An operator who opens the
named constant, finds it fine, and decides the line is lying is exactly the
reader the line exists for.

**Why:** gzapp #917, 2026-09-21. One clause about the fold-stamp derivation
(Makefile header, the re-import runbook §3, the NOT CHECKED string) took
four review rounds across three roles. My own suggested rewording ("when
both constants can be read") had the inverted quantifier, and db-admin caught
it (01a0c519-afa3). Then the same inversion turned up one layer down, in the
runtime string. devex-tooling ended it (f0c4b379) by removing the quantifier:
the define returns `missing`, and the line names the constant that failed.
That is also the one thing the operator needs: which file to open.

**How to apply:** when a message, log line or doc describes a failure of an
AND or OR guard, report the failing part by name (compute it beside the
verdict) instead of quantifying over the parts. When a quantifier cannot be
avoided in prose, read the sentence's negation aloud before committing it, and
write EITHER or ANY for an AND guard's failure. When suggesting wording to
another role, apply the same check to your own suggestion. Related:
[[latin-fold-dj-pair]], [[a-change-sweeps-the-prose-that-states-the-old-fact]].

*References: a-change-sweeps-the-prose-that-states-the-old-fact, latin-fold-dj-pair*

*Observed 2026-10-25 (backend-dev)*
