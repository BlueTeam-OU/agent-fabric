---
role: "devex-tooling"
class: domain
topic: "git-ancestry-no-needs-full-clone-and-base"
description: "in forge tooling, merge-base --is-ancestor's NO is a fact only in a non-shallow clone, and 'inside this PR' means inside base..head, so test the base too; a YES is a fact anywhere"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 01760be2cb383e6f
---

## in forge tooling, merge-base --is-ancestor's NO is a fact only in a non-shallow clone, and 'inside this PR' means inside base..head, so test the base too; a YES is a fact anywhere

commit_class's fold reading (agent-fabric #130 and #134, 2026-10-09) needed two review rounds:

1. **Range, not tip.** The rule is "a PR closed unmerged whose head is inside this range". I tested
   only `merge-base --is-ancestor <N head> <head>`. A PR folded into an earlier PR that has since
   merged sits in the base too, so a later follow-up answering it read as a fix. The fold now needs
   N's head to be an ancestor of head and not of base. Each caller passes the base it has:
   count_commits passes `origin/<base>`, pr_compliance passes `<merge>^1`.
2. **A no from a shallow clone is not a fact.** In a shallow clone, `--is-ancestor` exits 1 when
   the path is cut at the shallow boundary, and the code read that as "not inside". A yes holds in
   any clone. A no is believed only when `rev-parse --is-shallow-repository` says `false`.
   Otherwise the PR is unread: the safe reading, named on stderr.

**How to apply:** for any ancestry question in tooling ("landed?", "folded?", "in the range?"),
write down the range's two ends and test both. Ask the clone whether it is shallow before trusting
a negative answer. Test the shallow case with a real `--depth 1 --no-single-branch` clone that cuts
the path, not only with an injected git error. Related: [[gh-merge-fails-but-merges]] and
[[job-landed-check-by-commit]], which both lean on `--is-ancestor`.

*References: gh-merge-fails-but-merges, job-landed-check-by-commit*

*Observed 2026-10-22 (devex-tooling)*
