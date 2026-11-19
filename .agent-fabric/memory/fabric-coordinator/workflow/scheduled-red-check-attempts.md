---
role: "fabric-coordinator"
class: workflow
topic: "scheduled-red-check-attempts"
description: "a scheduled-red job may name a run that a re-run since turned green; read its attempts before diagnosing, and a green re-run of the same sha means a transient (j672)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 07885a08d9201317
---

## a scheduled-red job may name a run that a re-run since turned green; read its attempts before diagnosing, and a green re-run of the same sha means a transient (j672)

A `[scheduled-red:…]` job names a run id. By the time someone reads it, `gh run list` can show that run as `success`, because a later attempt of the same run passed. That happened on 2026-11-09 with run 42470679615: attempt 1 was red and attempt 2 was green. `gh run view --log-failed` then prints nothing.

To see what actually failed, read `gh api repos/<o>/<r>/actions/runs/<id>/attempts/1/jobs` for the failed steps, then `actions/jobs/<job-id>/logs` for the log.

If a later attempt on the same `head_sha` is green, the failure was transient, outside the tree. The fix is then resilience at the step that failed, not a test fix. In j672 that step was `python_pin.py install`: it got `HTTP Error 504` from the download host, and `_download` tries once with no retry. The retry was contracted to python-dev-03 as a supply-tier `for/user/j672-python-pin-retry` branch (REQUEST 01a1be88).

Related: [[j541-stripped-nightly-red]].

2026-11-13 (j843): I contracted run 43412779972, red at 600c5dcb, to python-dev-03 about 11 h after it ran. All three of its reds had already been fixed on main (430cc74e, b9a4f720, both in #587), so python-dev-03 spent a session confirming nothing was left. Before contracting a scheduled red, check two things: whether any commit since the run touched the failing files (`git log <run-sha>..origin/main -- <files>`), and what a fresh run says (`gh workflow run stripped-nightly.yml` on main). Contract only what is still red.

*References: j541-stripped-nightly-red*

*Anchors: `tools/fabric/python_pin.py::_download`, `tools/fabric/github/scheduled_red.py`*

*Observed 2026-11-09 (fabric-coordinator)*
