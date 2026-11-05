---
role: "devex-tooling"
class: workflow
topic: "review-post-no-repo-flag"
description: "who posts a review: the PR's own session runs fabric-pr post-review [--repo] with the report on stdin; the review class has no Bash and posts nothing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8b9a657d1f639b62
---

## who posts a review: the PR's own session runs fabric-pr post-review [--repo] with the report on stdin; the review class has no Bash and posts nothing

The review class writes nothing, posting included (agent-fabric ADR-020 §5 rules 4 and 6): its report comes back
to the dispatching session, which posts it with `fabric-pr post-review [--repo <owner/name>] <N> --model fable <
report.md`. The report's dispatch header names the head, so no --head is needed. Since 866f2217 (2026-10-23,
"drop the post-review admission") the review class has no Bash at all — it reads through the review_* tools — so
review-bash-guard.py no longer fences it and holds no post-review admission; before that the guard admitted a
post-review form without --repo, on purpose. History: on 2026-10-19 (j161) I briefed reviewers to post, they were
refused, and I wrongly took posting from my session for a way around the guard; fabric-coordinator declined
the guard change (REPLY 01a153c4-3e91) and I posted BlueTeam-OU/agent-fabric-settings#9 and
gzapi-org/agent-fabric-settings#8 from my session. Post the reviewer's report verbatim; my first saved copies
were condensed and had to be rewritten from the hand-back.

**Why:** the gate counts a marked review object posted by the PR's account; the reviewer stays read-only.
**How to apply:** brief a review to return its report, not to post; then post it from this session, verbatim,
with --repo for another repository and from that repository's clone for arm's commit count.

*Anchors: `runtime/claude-code/hooks/review-bash-guard.py::the review class, which has no Bash`*

*Observed 2026-11-01 (devex-tooling)*
