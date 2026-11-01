---
role: "fabric-coordinator"
class: workflow
topic: "budget-prose-read-back-by-import"
description: "an ADR quotes a control op's budget in seconds — read the number back by importing the module, never by adding the formula by hand"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fb4e984e3642b38f
---

## an ADR quotes a control op's budget in seconds — read the number back by importing the module, never by adding the formula by hand

ADR-029 §5 rule 12 quotes every `fabric-ctl` budget in seconds, and those numbers are sums of
constants in `tools/fabric/control/*.py`. Whenever a term in a sum changes, the prose falls behind
the code without anything failing. #392 added `DIAGNOSIS_BUDGET_S` (20 s) to `CHECK_BUDGET_S`, which
moved `interweave-install` from 2668 s to 2708 s and `interweave-start` from 1600 s to 1620 s. Fixed
in j414 (27a4ac64, on #429).

Read the numbers back by importing the module, never by redoing the arithmetic:
`PYTHONPATH=tools:communication python3 -c 'from fabric.control import carrier_install as c; print(c.CARRIER_START_BUDGET_S)'`
(`gzcoord` needs `communication/` on the path). Do this for every budget a PR touches.
Adding a DIGEST bullet can push an entry over the 250-word cap. Trim it without losing a word that
lookups use: [[digest-trim-keeps-lookups]].

*References: digest-trim-keeps-lookups*

*Anchors: `tools/fabric/control/carrier_install.py::CARRIER_START_BUDGET_S`, `docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md::12.`*

*Observed 2026-10-30 (fabric-coordinator)*
