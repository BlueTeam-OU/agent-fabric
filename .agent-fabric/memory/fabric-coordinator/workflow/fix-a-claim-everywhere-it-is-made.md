---
role: "fabric-coordinator"
class: workflow
topic: "fix-a-claim-everywhere-it-is-made"
description: Answering a review finding about a wrong claim, grep the whole change for the same claim before committing, or the next round finds it in a sibling file
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - daef20f95094f25a
---

## Answering a review finding about a wrong claim, grep the whole change for the same claim before committing, or the next round finds it in a sibling file

2026-10-19, blueteam.brand #4: round 1 said the remit's "the whole tree" wrongly included `.agent-fabric/`. I fixed the remit,
and round 2 found the same claim in `taxonomy.json`'s note ("brand-comms owns the tree"). blueteam.ee #14 cost a round the
same way: a remit quoted an owner point that AGENTS.md had already replaced (commit 8cd7e9d).

Third, gzapp #1129: I narrowed a hygiene pattern to `[Dd]cs` from two files of the [redacted] repository; the review found
`[redacted]` 300 times elsewhere in it, so the narrowing leaked the name. A claim about how a project writes something is
measured over its whole tree (`git -C <repo> grep -o -i`), and the new pattern is run over every use before it is
committed.

Fourth, agent-fabric #310 (2026-10-19): new hygiene patterns, measured over the local clones' working trees
with the drain branches skipped, "matched nothing else"; InterWeave main and herdr master each held a match,
so a sibling lint run would have gone red. A new refusal is measured over every project's `origin/main`
(`git grep <ref>`) and every open drain branch, and the PR states which merge must land first.

**Why:** every extra round is a dispatch, a post and a wait. A claim usually lives in more than one file of the same change.

**How to apply:** before an `Answers:` commit, `grep -rn` the PR's files for the finding's wording and its synonyms. Before
quoting a project's file in a remit, read that file on `origin/<default>` today, not as remembered. Related:
[[fold-then-full-suite]].

*References: fold-then-full-suite*

*Anchors: `tools/fabric/github/commit_class.py::trailer_values(body, "Answers")`, `policies/hygiene.json::refer_as`*

*Observed 2026-10-19 (fabric-coordinator)*
