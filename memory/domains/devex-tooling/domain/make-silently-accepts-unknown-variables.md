---
role: "devex-tooling"
class: domain
topic: "make-silently-accepts-unknown-variables"
description: GNU make takes any VAR=value on the command line and ignores it unless a recipe reads it, so a misspelt or inapplicable knob runs the default path silently; a target refuses the known wrong names and says when a knob is ignored
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4278bd09107f630b
---

## GNU make takes any VAR=value on the command line and ignores it unless a recipe reads it, so a misspelt or inapplicable knob runs the default path silently; a target refuses the known wrong names and says when a knob is ignored

`make <target> NAME=value` never fails because NAME means nothing. A variable no recipe expands is
silently nothing. The same thing happens when a knob is read only inside a branch that is not taken,
for example inside `$(if $(wildcard …), …)`. Two cases in gzapp's Makefile: `make backend-test
FILTER=AdServingTests` ran the whole suite for weeks, and the docs taught it (#896). And
`GZAPP_LEASE_WAIT=900` vanished on a checkout with no lease script, neither waiting nor saying so
(#916). Neither run gave any signal: the run is green, just not the run that was asked for.

**How to apply:** for a make target you own that takes knobs:
- refuse a name people actually reach for that the target does not read:
  `ifeq ($(origin FILTER),command line)` → `$(error …)`, naming the real knob;
- when the current path ignores a knob it does read elsewhere, print `<knob> is IGNORED — <why>`;
- test both cases through the real recipe.

When a make run "worked" but did not do what was asked, check first whether the variable you passed
is one the recipe actually expands (`make -n`, `make -p | grep NAME`). Related:
[[npm-ci-scripts]] (`--if-present` is the same silent no-op).

*References: npm-ci-scripts*

*Observed 2026-10-22 (devex-tooling)*
