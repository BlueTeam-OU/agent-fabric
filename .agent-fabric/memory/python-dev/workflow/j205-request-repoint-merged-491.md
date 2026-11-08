---
role: "python-dev"
class: workflow
topic: "j205-request-repoint-merged-491"
description: "j205 merged in #491 - request blocker re-points to the job it became; arm --defer syntax, count rule was 1, re-review chaining, parts import order"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 77fc2194f6c17b27
---

## j205 merged in #491 - request blocker re-points to the job it became; arm --defer syntax, count rule was 1, re-review chaining, parts import order

j205 (#491): blockers.check_request reads the answerer's board (read_board) for a title ending "(REQUEST <mid>)", else one body token; refresh() re-points under mutate AFTER the cache merge, never inside the lock. request_id_of moved to jobsparts/base.py because test_jobs_parts bans a part importing a later one (records is after blockers) - the full suite found it, the targeted suites did not.

**Why:** a REPLY "taken as j7" cleared the blocker with nothing delivered (four times).
**How to apply:**
- A board row id or a body token is another agent's text: store it only if JOB.fullmatch(f"job:{login}/{id}") holds (review F2).
- fabric-pr arm refuses on an open P2/P3 in a review chain: `--defer "<head8>:F<n>" "<why>"` per finding, after the owner's word; the agent-fabric count rule was 1 work commit here, not 8 - run `arm --dry-run` with a basis before quoting a minimum.
- A re-review round's next request is derived from the PREVIOUS round's req-rr<n>.json (`fabric-review next <that> --pr N --head <sha>`), not the first request; brief the generated json, dispatch verbatim, `fabric-review save N <round>` first.
- A push needs `git -c credential.helper='!gh auth git-credential' push`, alone with the literal worktree path (job guard).

*Observed 2026-11-05 (python-dev)*
