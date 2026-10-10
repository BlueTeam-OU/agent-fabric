---
role: "fabric-coordinator"
class: workflow
topic: "pr-band-accumulate"
description: One open PR per agent; eight or more work commits arm at the review gate; the next piece of work is another commit
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 029add46709fe07a
  - 2324a79955f986c3
---

## One open PR per agent; eight or more work commits arm at the review gate; the next piece of work is another commit

ONE open pull request per agent (ADR-019, team.md): while a PR is open, the next piece of work is another commit on it if the branch is addable, else it waits for the merge and is built locally. Concerns are commit boundaries, not PR boundaries. Exceptions, stated in the new PR's description: a finding on the queued PR itself; urgency (user-visible or CI-blocking).

Eight or more work commits arm once the review gate is met; there is no upper bound on arming (sixteen is only the size a batch is opened at). Fewer: ask the owner. Work commits are counted by each commit's `Kind:` trailer, so `Kind: review-fix` commits do not count.

**Why:** two one-commit PRs in one morning drew the owner's "must stay in the same pr"; the rule has exceptions, so do not over-correct to "none".

**How to apply:** before `gh pr create`, count the `Kind: work` commits on `origin/main..HEAD`; under eight, keep working on the branch. Fold a stray branch in unrebased (`git merge --no-ff`) and close its PR naming where it went. See [[blind-review-loop]].

*References: blind-review-loop*

*Observed 2026-10-10 (fabric-coordinator)*
