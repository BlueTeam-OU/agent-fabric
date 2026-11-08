---
role: "python-dev"
class: workflow
topic: "j117-suite-run-marker-delivered"
description: j117 resume.SUITE_MARKER renamed to AGENT_FABRIC_SUITE_RUN, delivered as a for/user branch; hook traps
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9bc388c997d8af3a
---

## j117 resume.SUITE_MARKER renamed to AGENT_FABRIC_SUITE_RUN, delivered as a for/user branch; hook traps

j117 delivered 2026-11-05: 6cdc2e5a on develop-qzapp/python-dev-02/for/user/suite-run-marker (no PR). resume.SUITE_MARKER
= AGENT_FABRIC_SUITE_RUN; test_resume_profiles_marker has a case where AGENT_FABRIC_TEST_JOBS alone is no marker.

**Why:** the runner line (tests/run.py run_environment) was the requester's, on their PR #488; origin/main's runner
did not set the marker yet, so the full suite passed without exercising it through the runner.

**How to apply:** the job-copy hook refuses `git commit` chained after `mkdir "$TMPDIR"`/variable paths in one Bash call —
commit alone. `fabric-jobs switch` refuses until `fabric-jobs deliver <id> <sha>`, every REPLY-EXPECTED request
answered (even a new one that arrived meanwhile) and a memory file written. See [[j116-suite-run-marker-delivered]].

*References: j116-suite-run-marker-delivered*

*Anchors: `tools/fabric/resume.py::AGENT_FABRIC_SUITE_RUN`*

*Observed 2026-11-05 (python-dev)*
