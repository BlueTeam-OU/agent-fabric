---
role: "devex-tooling"
class: domain
topic: "make-shell-arguments-cannot-hold-unbalanced-parens"
description: "A `case … *)` (or any unbalanced `)`) inside a Makefile $(shell …) ends the call early and the rest of the text becomes the value; and a value substituted into a $(shell bash -c '…') string is shell text at parse time on every make."
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2c635a00bc796480
---

## A `case … *)` (or any unbalanced `)`) inside a Makefile $(shell …) ends the call early and the rest of the text becomes the value; and a value substituted into a $(shell bash -c '…') string is shell text at parse time on every make.

Two traps met on 2026-09-17 in gzapp's Makefile resolver (#839):

1. `$(shell bash -c '… case "$$w" in *) …; esac …')` — make matches
   parentheses when parsing the `$(shell` argument, so the `)` in a
   case arm closes the call; the output read "w=NONE" because the
   text after that `)` had become the variable's value. Use `[[ "$w"
   =~ ^…$ ]] || w=NONE` or another construct with balanced parens.
2. `$(shell bash -c '… "$(GZAPP_VAR)" …')` substitutes the variable
   into the command string before bash parses it: a value carrying a
   quote is executed at parse time, on every `make` invocation
   (`make help` included). Read the value inside the shell instead —
   `$(shell)` inherits the environment — and validate it there.

**How to apply:** in a `$(shell …)`, no unbalanced parentheses, and
no make-expanded value inside the shell text; the make precheck suite
has an injection case for the GTFS version.

*References:  "$w"
   =~ ^…$ *

*Observed 2026-09-17 (devex-tooling)*
