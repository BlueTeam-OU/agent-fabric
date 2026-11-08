---
role: "python-dev"
class: solution
topic: "j115-suite-marker-profiles-merged"
description: "j115 #490 merged; resume.profile_provider reads no profile under a suite marker; follow-up j116 renames marker to AGENT_FABRIC_SUITE_RUN (patch saved)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 037b276dea1ccc5e
---

## j115 #490 merged; resume.profile_provider reads no profile under a suite marker; follow-up j116 renames marker to AGENT_FABRIC_SUITE_RUN (patch saved)

#490 (1 work, 1 fix, head 5bfd95dc, merged 75f071d3): `resume.profile_provider()` returns None when `AGENT_FABRIC_RESUME_PROFILES` is unset/empty and the suite marker is set; only `tests/test_fabric_resume.py` relied on the live file (found by tracing the live-path fall-through over a full run, then reverting the trace).

**Why:** `AGENT_FABRIC_TEST_JOBS` is set by run.py only while it holds a cpu slot (not in CI, opt-out, by-hand runs), so the coordinator agreed (reply seq 846596) to a dedicated `AGENT_FABRIC_SUITE_RUN=1` in run_environment (theirs); mine is SUITE_MARKER in resume.py plus the marker test, delivered as `develop-qzapp/python-dev-02/for/user/suite-run-marker` (no PR), job j116. The finished patch is at `~/agent-fabric-tmp/j116-suite-run-marker.patch` (apply on a branch from origin/main, mutation `if False:` fails the marker test).

**How to apply:**
- A commit is refused once the session's job left active: `fabric-jobs add --request <id>` (no title with --request), then switch; save uncommitted work as a patch first, switch refuses a dirty copy and an unchanged memory dir.
- A full `tests/run.sh python` under host load goes red on test_leak_check, test_langid_install_quiet, test_jobs_switch; each passes alone.
- `fabric-review brief` takes `<request.yaml>`; a re-review request must not carry previous_findings; `fabric-review save <pr> 1 < report` before the re-review brief.

*Anchors: `tools/fabric/resume.py::profile_provider`*

*Observed 2026-11-05 (python-dev)*
