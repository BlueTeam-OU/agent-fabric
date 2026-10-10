---
role: "python-dev"
class: workflow
topic: "ci-env-for-lint-and-mutations"
description: "Run lint.py and mutation harnesses with AGENT_FABRIC_* stripped and a scratch TMPDIR — the session env makes lint check the main checkout and mutations leak into the account TMPDIR"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b7d11048b3aadc8
---

## Run lint.py and mutation harnesses with AGENT_FABRIC_* stripped and a scratch TMPDIR — the session env makes lint check the main checkout and mutations leak into the account TMPDIR

The session shell exports AGENT_FABRIC_ROOT=<main checkout>, so
`python3 tools/fabric/lint.py` run in a worktree lints MAIN, not the
worktree: it said "clean" over five generic-file findings that the
suite (which strips AGENT_FABRIC_*) then failed on (2026-10-08, forge
port branch). Run it as the suite does: env -u each AGENT_FABRIC_*/
GITHUB_* var and GIT_DIR.

A mutation harness runs the code with a defect planted on purpose — a
"marker removed" mutation of run_suite left six marker files in the
account TMPDIR. Give every mutation run its own TMPDIR under the
scratchpad and remove it after.

**Why:** both made a green look true that was not, or left state behind.
**How to apply:** every lint, suite and mutation run in a worktree:
strip the env, own the TMPDIR. See [[forge-port-oracle-runs]].

The suite's own TMPDIR must be SHORT: under the session scratchpad
(/var/tmp/…/claude-1020/<slug>/<session>/scratchpad/…) test_session_start
fails with "AF_UNIX path too long" and test_secret_store's recovery-copy
case fails too (gpg-agent socket); both pass with a TMPDIR of
/var/tmp/agent-fabric-<login>/x.XXXX (2026-10-08, PR #122). Use
`mktemp -d /var/tmp/agent-fabric-<login>/afs.XXXX` for suite runs.

Helpers kept outside the tree (2026-10-08): `. /var/tmp/agent-fabric-python-dev-02/cienv.sh; ci <cmd>` strips AGENT_FABRIC_*/GITHUB_*/GIT_DIR; CI's ruff 0.16.7 is in /var/tmp/agent-fabric-python-dev-02/ruff-venv/bin/ruff (not on the host otherwise). A PreToolUse hook refuses `check | filter && git commit`: run the check to a log, read rc, commit separately.

*References: forge-port-oracle-runs*

*Observed 2026-10-08 (python-dev)*
