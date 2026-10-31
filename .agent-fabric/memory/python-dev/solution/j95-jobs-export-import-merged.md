---
role: "python-dev"
class: solution
topic: "j95-jobs-export-import-merged"
description: "j95 fabric-jobs export|import merged (#401, 475136d1); transfer.py part, review traps (untrusted-document checks), CI interpreter trap for depth tests"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 33af9abda8e59dc8
---

## j95 fabric-jobs export|import merged (#401, 475136d1); transfer.py part, review traps (untrusted-document checks), CI interpreter trap for depth tests

`fabric-jobs export|import` (j422 gap F2) is `tools/fabric/jobsparts/transfer.py`, test `tests/test_jobs_transfer.py`; PR #401 merged 2026-10-27 (4 work, 5 fix), reply 01a17ccb sent to develop-qzapp/user.

- Document: format `fabric-jobs-export` v1: agent, host (recorded, not applied), seq, last, jobs, blocker_cache (entries for the specs the jobs name; `seen_open` cannot be re-derived on the destination). Import fills an EMPTY list only, checked under the list lock.
- Review rounds found the class "untrusted document reaches a renderer": check every string of a job and cache entry (keys included) for control characters, type every field the tool prints, require blockers equal `bl.normalise(spec)`, bound nesting (iterative walk, MAX_DEPTH 32; json.dumps recurses too).
- **Why:** a depth test that relies on json.loads giving up passes or fails by interpreter (CI's parsed 100000 deep, the pinned local one did not). **How to apply:** force the parser to fail with a stub (patch the module's `json`) and keep a real-document smoke case beside it.
- Carried P3 F8: depth refusal names no job id/cache spec. Open risks: paths travel verbatim; source list is not retired.
- `fabric-jobs deliver` marks the job delivered, and the PreToolUse hook then refuses commits: `fabric-jobs start <id>` again before more commits on the PR.

*Anchors: `tools/fabric/jobsparts/transfer.py::MAX_DEPTH`, `tools/fabric/jobsparts/transfer.py::def import_jobs`, `tests/test_jobs_transfer.py::GivesUp`*

*Observed 2026-10-27 (python-dev)*
