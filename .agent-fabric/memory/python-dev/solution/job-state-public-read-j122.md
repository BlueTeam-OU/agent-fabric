---
role: "python-dev"
class: solution
topic: "job-state-public-read-j122"
description: "j122 #527 — public job-state op, blockers.py peer reads, cycle refusal; review and arming traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc952259ab4c3c3a
---

## j122 #527 — public job-state op, blockers.py peer reads, cycle refusal; review and arming traps

#527 (4 work, 3 fix) merged: `job-state` is a PUBLIC op (control/jobs.py job_state, control/queue.py `job-state <login> <id>`); blockers.py asks it for a non-operator (queue.py answers `{"operator": true}` for an operator, who reads the board), a refusal counts as an unreadable board (body fallback), absent clears only a job seen open. Only the sender of the request (source kind `request`, source.from) is answered. The "second reader" (a login naming the job in its own blocker) is not built: that blocker is in the asker's own list, unreadable to the answering side.

**Why:** `jobs` is an operator's op, so a non-operator's `job:` blocker was unknown for ever and `request:` re-pointed by reply-body ids.

**How to apply:**
- Cycle refusal sees only the own list and boards an operator can read; a non-operator's peer board carries no blockers by design.
- `blockers.py` may import `queue` only because the parts order is base, ranking, queue, blockers (tests/test_jobs_parts.py ORDER, jobs.py facade).
- A test that seeds the journal (episodic.py) needs its own `.agent-id` store plus HOME, or it dies on a clean CI user; restore HOME as unset when it was unset.
- A security-boundary PR under 8 work commits arms only with the coordinator's DECISION (`AUTHORIZES: <repo>#<n>@<head>`, id via `--authorization`); a P3 in the coordinator's ADR text is `--defer`red and sent to them, never edited.
- `fabric-review next` prints the whole brief; the dispatch prompt can be a compact brief with the same dispatch header. A blocked job needs `fabric-jobs start` before a git merge/commit again.
- Live read-back after `fabric-ctl all upgrade fabric` is the coordinator's step; not done by me.

*Anchors: `tools/fabric/control/jobs.py::job_state`, `tools/fabric/jobsparts/blockers.py::_cycle`, `tools/fabric/control/queue.py::job_state_cli`*

*Observed 2026-11-09 (python-dev)*
