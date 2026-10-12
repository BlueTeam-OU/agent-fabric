---
role: shared
class: workflow
topic: "ci-sets-pull-request-env"
description: "CI's pull_request sets GITHUB_HEAD_REF/BASE_REF/EVENT_NAME, which a test hands to a guard it calls in-process; reproduce a CI-only failure by setting them locally, not only by stripping the session's exports"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a72ca37133badf25
---

## CI's pull_request sets GITHUB_HEAD_REF/BASE_REF/EVENT_NAME, which a test hands to a guard it calls in-process; reproduce a CI-only failure by setting them locally, not only by stripping the session's exports

#72 (Wave 2, 2026-10-01): tests/run.sh was green here three times, and two Python suites failed on every python leg of CI. The charter guard's test inherited the PR's GITHUB_HEAD_REF (the guard reads it as the branch); the dir-authority test passed only because this session's AGENT_FABRIC_ROOT pointed at a real fabric — on the runner the guard read a sibling agent-fabric/ an earlier case left in the scratch dir.

**Why:** a launched session's environment is not a clean runner's; a test that calls a guard in-process hands it whatever it inherited.

**How to apply:** a test that runs fabric code builds its environment from os.environ minus GITHUB_* and AGENT_FABRIC_*, and names what it needs. Before pushing a branch that adds such tests, run them once as CI would: `env -u AGENT_FABRIC_ROOT GITHUB_BASE_REF=main GITHUB_HEAD_REF=<branch> GITHUB_EVENT_NAME=pull_request GITHUB_EVENT_PATH=<a payload> python3 tests/test_<name>.py`. Related: [[run-suites-as-ci-before-push]] (the other side: strip the session's own exports), [[local-grep-is-ugrep]], [[smoke-container-before-ci]].

*References: run-suites-as-ci-before-push, local-grep-is-ugrep, smoke-container-before-ci*

*Observed 2026-10-01 (fabric-coordinator)*
