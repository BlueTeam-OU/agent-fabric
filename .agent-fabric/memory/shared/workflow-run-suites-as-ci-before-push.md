---
role: shared
class: workflow
topic: "run-suites-as-ci-before-push"
description: "A suite green in a launched session can fail in CI — the session sets AGENT_FABRIC_ROOT, CI's pull_request sets GITHUB_HEAD_REF/BASE_REF; run the touched suites with CI's environment before pushing"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a72ca37133badf25
---

## A suite green in a launched session can fail in CI — the session sets AGENT_FABRIC_ROOT, CI's pull_request sets GITHUB_HEAD_REF/BASE_REF; run the touched suites with CI's environment before pushing

#72 (Wave 2, 2026-10-01): tests/run.sh was green here three times, and two Python suites failed on every python leg of CI. The charter guard's test inherited the PR's GITHUB_HEAD_REF (the guard reads it as the branch); the dir-authority test passed only because this session's AGENT_FABRIC_ROOT pointed at a real fabric — on the runner the guard read a sibling agent-fabric/ an earlier case left in the scratch dir.

**Why:** a launched session's environment is not a clean runner's; a test that calls a guard in-process hands it whatever it inherited.

**How to apply:** a test that runs fabric code builds its environment from os.environ minus GITHUB_* and AGENT_FABRIC_*, and names what it needs. Before pushing a branch that adds such tests, run them once as CI would: `env -u AGENT_FABRIC_ROOT GITHUB_BASE_REF=main GITHUB_HEAD_REF=<branch> GITHUB_EVENT_NAME=pull_request GITHUB_EVENT_PATH=<a payload> python3 tests/test_X.py`. Related: [[local-grep-is-ugrep]], [[smoke-container-before-ci]].

*References: local-grep-is-ugrep, smoke-container-before-ci*

*Observed 2026-10-01 (fabric-coordinator)*
