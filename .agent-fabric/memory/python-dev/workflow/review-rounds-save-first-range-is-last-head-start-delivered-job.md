---
role: "python-dev"
class: workflow
topic: "review-rounds-save-first-range-is-last-head-start-delivered-job"
description: "fabric-review next order (post, save, range = last reviewed head), a delivered job cannot commit until started, a second intake path hides in gzcoord/intake.py"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e91b30eab1c53029
---

## fabric-review next order (post, save, range = last reviewed head), a delivered job cannot commit until started, a second intake path hides in gzcoord/intake.py

j66 / PR 372 (2026-10-24), four review rounds, traps beyond [[review-next-needs-card-base-and-json-request]] and [[review-base-must-be-ancestor-merge-main-first]]:

- `fabric-review next REQ --pr N --head H` needs the round saved first (`fabric-review save N <round> < report`) and the request's `range:` must be `<last base>..<last reviewed head>` as full shas; it writes `<req>-rr<k>.json` and you render that with `fabric-review brief`.
- After `fabric-jobs deliver`, the guard refuses git commit/push (job left `active`): `fabric-jobs start <id>` resumes the delivered job for review fixes. Run git from the worktree with an explicit `cd` in the same command, or the guard cannot resolve it.
- A change to how a REQUEST becomes a job has TWO writers, `jobsparts/records.py request_job` and `gzcoord/intake.py` (receiver half `queue_received`, sender half `queue_for_addressee` via control-plane jobs-add): whichever adds first names the project. Review caught it; grep `new_job(` and `jobs-add` callers before calling intake done.
- Full `tests/run.sh python` on this host under other agents' suites exceeds 30 min and trips timing-bound gzcoord cases; run the touched suites alone and say so.

**Why:** each cost a round or a rerun. **How to apply:** save before next; grep all writers of the field you change.

*References: review-base-must-be-ancestor-merge-main-first, review-next-needs-card-base-and-json-request*

*Anchors: `tools/fabric/gzcoord/intake.py::queue_for_addressee`, `tools/fabric/jobsparts/records.py::request_project`*

*Observed 2026-10-24 (python-dev)*
