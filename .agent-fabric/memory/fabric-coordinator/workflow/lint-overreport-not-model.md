---
role: "fabric-coordinator"
class: workflow
topic: "lint-overreport-not-model"
description: "A guard lint whose fix is always safe should over-report on the language's static scoping, not model runtime order — #143's $ rule took four review rounds learning this"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91946690bd549d0c
  - e7763074f2698e56
---

## A guard lint whose fix is always safe should over-report on the language's static scoping, not model runtime order — #143's $ rule took four review rounds learning this

The `$`-pattern lint (tools/fabric/lint_rules/regex.py) went through four blind-review
rounds on #143 (2026-10-09): each round's fix of an ordered model of Python's bindings
(source order, rebinding cancels, module-level calls at their line) opened new misses
(aliases, closures, a call before a rebinding, subclass redefinitions).

**Why:** when the remedy a finding asks for is always correct (here `.fullmatch` is
never wrong for an anchored pattern), a false finding costs a harmless edit and a miss
costs the bug. Precision is not worth a model that can under-report.

**How to apply:** for a guard of that kind, resolve names by the language's static,
order-free scoping (a name bound anywhere in a function is local; any risky binding in
a scope makes the name risky there) and over-report by design; say so in the rule's
docstring so the next reviewer does not file the intended over-reports as defects.

**Applied again, 2026-10-21, #348 (job-copy guard):** two regressions came from modelling instead of over-reporting. In round 2, scoping "heredoc executed" to its pipeline missed `{ bash; } <<X`, `|& bash` and `while … eval`; the fix was a runner word anywhere in the command reading every body. In round 4, my own one-word lookback for the dot command missed `x=1 . /dev/stdin`. When narrowing an over-report to remove a false deny, narrow by the grammar's full prefix (assignments, redirections), never by one neighbouring word, and add the bypass shapes as tests before committing.

*Observed 2026-10-09 (fabric-coordinator)*
