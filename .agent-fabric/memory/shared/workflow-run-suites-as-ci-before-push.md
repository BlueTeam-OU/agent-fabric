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
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a72ca37133badf25
  - f58b9bf384d40aca
---

## Running a suite "as CI" — strip CLAUDE_* and ANTHROPIC_* as well as AGENT_FABRIC_*/GITHUB_*/GIT_DIR; a launched session's own exports satisfy assertions CI would fail

A session started by runtime/openrouter/launch carries the launcher's
exports — CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1, ANTHROPIC_DEFAULT_*_MODEL,
CLAUDE_CODE_OAUTH_TOKEN and the rest — and a suite that does not clear them
passes them to what it tests. In the Wave 4 mutation run (2026-10-01,
agent-fabric branch develop-qzapp/python-dev-01/for/user/wave-4-launcher)
a mutation deleting the launcher's terminal-title export SURVIVED
test_launch.sh: the fake child read the variable the session had
inherited. Re-run with CLAUDE_* and ANTHROPIC_* stripped, the oracle
killed it, as a CI runner would.

**Why:** stripping only AGENT_FABRIC_*, GITHUB_* and GIT_DIR leaves the
launch's own environment in, so a test of what the launcher exports can be
green for the wrong reason, and a mutation run reads it as a coverage gap
(or hides one).

**How to apply:** for a CI-like local run, unset every name starting
AGENT_FABRIC_, GITHUB_, CLAUDE_ or ANTHROPIC_, and GIT_DIR, e.g.
`strip=(); for v in $(compgen -e); do case "$v" in AGENT_FABRIC_*|GITHUB_*|GIT_DIR|CLAUDE_*|ANTHROPIC_*) strip+=(-u "$v");; esac; done; env "${strip[@]}" bash tests/run.sh`.
A test that needs one sets it itself. Related: [[run-suites-as-ci-before-push]].

*References: run-suites-as-ci-before-push*

*Observed 2026-10-10 (python-dev)*

## A suite green in a launched session can fail in CI — the session sets AGENT_FABRIC_ROOT, CI's pull_request sets GITHUB_HEAD_REF/BASE_REF; run the touched suites with CI's environment before pushing

#72 (Wave 2, 2026-10-01): tests/run.sh was green here three times, and two Python suites failed on every python leg of CI. The charter guard's test inherited the PR's GITHUB_HEAD_REF (the guard reads it as the branch); the dir-authority test passed only because this session's AGENT_FABRIC_ROOT pointed at a real fabric — on the runner the guard read a sibling agent-fabric/ an earlier case left in the scratch dir.

**Why:** a launched session's environment is not a clean runner's; a test that calls a guard in-process hands it whatever it inherited.

**How to apply:** a test that runs fabric code builds its environment from os.environ minus GITHUB_* and AGENT_FABRIC_*, and names what it needs. Before pushing a branch that adds such tests, run them once as CI would: `env -u AGENT_FABRIC_ROOT GITHUB_BASE_REF=main GITHUB_HEAD_REF=<branch> GITHUB_EVENT_NAME=pull_request GITHUB_EVENT_PATH=<a payload> python3 tests/test_X.py`. Related: [[local-grep-is-ugrep]], [[smoke-container-before-ci]].

*References: local-grep-is-ugrep, smoke-container-before-ci*

*Observed 2026-10-01 (fabric-coordinator)*
