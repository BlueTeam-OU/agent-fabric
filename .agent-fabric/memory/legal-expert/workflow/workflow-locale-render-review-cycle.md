---
role: "legal-expert"
class: workflow
topic: "workflow-locale-render-review-cycle"
description: Order of a Georgian locale render of a role text — two passes, cold read of the fix, then one delivery; budget cuts never drop a rule
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4a6def1f45ae0287
  - 6f8f12b4c95e4bd5
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

**When language-culture-ge renders the same English change in its own Georgian file** (e.g. identities/prompt/locale/ge/team.md, which sits beside my identities/roles/legal-expert/locale/ge/team.md), its proposed fix may be word for word its already cold-read sentence. If the sentence and the lines before it are identical in both files (check with `git show <its branch>:<path>`), that cold read stands in for mine. Say so in the fix commit and name the passes as `Translation-Review-Pass-1/-2` trailers. That made one delivery possible in j19 (2026-10-19, d1e6f072; REPLY 01a1542d). Answer each finding first for legal effect: in j19, "უფლებამოსილი" takes "-ზე", not the genitive, and a bare Latin "dry-run" reads as a noun, so refer back to the command instead (იგივე ბრძანება).

**An ambiguous English noun is rendered by its antecedent, not literally** (j21, 2026-10-24, e22c351c; REPLY 01a16f23). "A decision written only on your own screen" (team.md, after "Blocked on another agent's decision") left both readings open in English. A literal "გადაწყვეტილება, რომელიც … შენს ეკრანზე წერია" reads in Georgian as the reader's own decision and loses the antecedent. language-culture-ge's "საკითხი, რომლის გადაწყვეტასაც ელოდები, თუ …" keeps the rule. Keeping a source ambiguity is right only if the Georgian keeps it too; check what the literal noun picks. The opposite holds as well: a condition a draft adds ("თუ მის REQUEST-ზე მუშაობ") is dropped when the source has none. One request-acceptance commit: amend the local commit with the trailers and push once. A job blocked on the review request must be `fabric-jobs start`ed again before the commit hook allows the commit.

**Look for language-culture-ge's branch of the same request first** (j24, 2026-10-28, c8212802; REPLY 01a181d1). A coordinator request that makes both ge copies lag usually goes to both holders with the same branch suffix (`…/language-culture-ge/for/user/j412-team-background`). Fetch it before asking for passes. If its paragraph is already two-pass reviewed and the lines before it match, adopt it word for word and cite its commit in the trailers. That makes one delivery possible with no review round trip. In j24 its wording also avoided a Latin `cpu` (პროცესორის სლოტი).

*References: holder-launch-check, workflow-charter-translation*

*Anchors: `tools/fabric/lint_rules/prompts.py::LOCALE_BUDGET_FACTOR`, `tools/fabric/lint_rules/prompts.py::TIER1_BUDGET_TOKENS`*

*Observed 2026-10-18 (legal-expert)*
