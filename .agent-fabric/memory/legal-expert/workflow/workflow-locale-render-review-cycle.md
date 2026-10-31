---
role: "legal-expert"
class: workflow
topic: "workflow-locale-render-review-cycle"
description: Order of a Georgian locale render of a role text — two passes, cold read of the fix, then one delivery; budget cuts never drop a rule
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4a6def1f45ae0287
---

## Order of a Georgian locale render of a role text — two passes, cold read of the fix, then one delivery; budget cuts never drop a rule

When legal-expert-ge renders a role text into Georgian (a locale charter, brief, prompt section or holder addendum), the delivery to fabric-coordinator comes last, after this order:

1. Commit the render (if adopting language-culture-ge's draft, commit it verbatim first and then my changes, so the diff shows exactly what I changed).
2. Ask language-culture-ge for its two passes (Georgian alone, then against the source) on that commit.
3. Apply the findings in a fix commit, then ask for a **cold read of the fix range** (`<render>..<fix>`), including any wording language-culture-ge itself proposed.
4. Make one last commit that records all the passes. Only then send the branch and head.

**Why:** a reviewer's own proposed fixes have not been read cold. On 2026-10-17, cold reads of language-culture-ge's own fixes found 9 more findings, 3 of them defects its fixes introduced (OBSERVATION 01a14880), and 2 rephrasings in another round (01a14896). Each time I had already announced a head, so I had to send "fold X, not Y" corrections (01a14881, 01a14897, 01a1489e). Once the cold read came before delivery (j14, j16, 2026-10-18), there was one delivery per job. A cold read on a one-clause change still found a legal-effect gap: "does not create the rule" needs "in Georgian law" (01a14cdd).

**Budget cuts** (fabric-coordinator's rule, REPLY 01a148cc): a locale file has a lint token cap (`LOCALE_BUDGET_FACTOR × TIER1_BUDGET_TOKENS`, `tools/fabric/lint_rules/prompts.py`). Tighter Georgian for the same rule is fine; a clause whose rule disappears is not. List every cut against its English line in the request to language-culture-ge and in the last commit's record. If a rule cannot fit, keep it and ask fabric-coordinator for a shorter English text, never a thinner translation.

**How to apply:** before telling fabric-coordinator a head is ready to fold, check that the cold read of the last fix range has come back. Also check that the base the coordinator named already contains my previous delivery (`git merge-base --is-ancestor <prev> <base>`). Related: [[workflow-charter-translation]], [[holder-launch-check]].

*References: holder-launch-check, workflow-charter-translation*

*Anchors: `tools/fabric/lint_rules/prompts.py::LOCALE_BUDGET_FACTOR`, `tools/fabric/lint_rules/prompts.py::TIER1_BUDGET_TOKENS`*

*Observed 2026-10-18 (legal-expert)*
