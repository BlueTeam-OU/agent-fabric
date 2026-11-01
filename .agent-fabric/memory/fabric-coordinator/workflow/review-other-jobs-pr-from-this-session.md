---
role: "fabric-coordinator"
class: workflow
topic: "review-other-jobs-pr-from-this-session"
description: "Reviewing a PR that belongs to another of my jobs from this session: set job_id in the request, save the round, queue the posting — post-review is refused outside the session's job"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35836699ea5e061a
---

## Reviewing a PR that belongs to another of my jobs from this session: set job_id in the request, save the round, queue the posting — post-review is refused outside the session's job

2026-10-28, in the j412 session I re-reviewed #417 (job j422) to unblock it:
- `fabric-review brief` stamps the dispatch header's `job_id` with the session's *active* job (j412), not the PR's job. Set `"job_id": "j422"` in the request so the round is booked to the right job.
- No previous request was saved for the PR (`round-N.json` holds only `{"evidence_mode": ...}`), so `fabric-review next` cannot be used. Write the request by hand with these fields: repository (the local path), mode re-review, range (last posted review's head..PR head, read from the `agent-fabric-review v2` marker of the newest PR review), card_base (that marker's `card=`), pr, review_id, review_round, `evidence` (the key is `evidence`, not `evidence_mode`), and lenses.
- The one-job guard (ADR-037 rule 3) refuses `fabric-pr post-review` run in the other job's worktree. Reading and dispatching are allowed. Save the report with `python3 tools/fabric/review_rounds.py save <PR> <round> --repo <worktree dir name>` (this also removes the pinned head worktree), then queue a job naming the saved path and the findings to answer (j454).

**Why:** the dispatch, the save and the post must all point at the PR's own job; posting from the wrong session is refused at the very end of the work.
**How to apply:** do this only when the review unblocks this session's job. Otherwise queue the review in the PR's own job. Related: [[review-request-fields]], [[job-in-other-repo-needs-fresh-session]].

*References: job-in-other-repo-needs-fresh-session, review-request-fields*

*Anchors: `tools/fabric/review_rounds.py::card_base`*

*Observed 2026-10-28 (fabric-coordinator)*
