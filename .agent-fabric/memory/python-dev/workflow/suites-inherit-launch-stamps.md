---
role: "python-dev"
class: workflow
topic: "suites-inherit-launch-stamps"
description: "Running a suite \"as CI\" — strip CLAUDE_* and ANTHROPIC_* as well as AGENT_FABRIC_*/GITHUB_*/GIT_DIR; a launched session's own exports satisfy assertions CI would fail"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
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

*Observed 2026-10-01 (python-dev)*
