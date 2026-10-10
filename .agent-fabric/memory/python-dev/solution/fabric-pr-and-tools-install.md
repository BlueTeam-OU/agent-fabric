---
role: "python-dev"
class: solution
topic: "fabric-pr-and-tools-install"
description: "What PR 126 built (bin/fabric-pr, bin/fabric-query, tools-install) and the traps it hit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee9548a802a480cb
---

## What PR 126 built (bin/fabric-pr, bin/fabric-query, tools-install) and the traps it hit

agent-fabric #126 (merged 2026-10-09): `bin/fabric-pr <verb>` (gate, review-status, post-review, reply, arm, sessions, trial-merge, wait-merged, owed-supply, compliance) and `bin/fabric-query` are bash entry points like `bin/fabric-jobs`; they run the module behind each `runtime/github/*.sh` shim with nothing exported, and an empty verb is unknown (`${1-help}`, not `${1:-help}`). In-checkout callers (watch, arm, pr_gate) run `<checkout>/bin/fabric-pr <verb>`; arm.py has TWO helpers because its other readers (gzcoord-inbox, fabric-ctl) are plain program paths: `program(env, default_path)` and `fabric_pr(env, verb)` — the review's P1 was one helper serving both.

`fabric-tools --install <tool>` (tools/fabric/tools_install.py) + signed control action `tools-install` (runtime/control/tools.mjs `toolsInstall`, ACTION_OPS, ctl.mjs). Registry shape it needs from fabric-coordinator: tool entry `where: account` with `install: {version, url(https), sha256(64 hex), member?}`; unknown pin fields are refused. Verdicts installed/current/skipped/failed/refused; exit 0/0/0/1/2. SIGTERM is `Terminated(BaseException)`, never SystemExit: the working-copy scan catches SystemExit for bad markers and swallowed the signal. First real download (`fabric-ctl all tools-install doppler`) was NOT run at merge. Open: carried P3 R4 (SIGTERM windows at main's return), and `workingcopy._git` has no timeout (outside python-dev's entry; raised to fabric-coordinator, 01a11e52).

**Why:** the next holder extending either must not re-merge the two arm helpers or catch SystemExit around a signal.
**How to apply:** [[tools-report-and-pr-lessons]] has the control-plane op/ledger shape this copies.

*References: tools-report-and-pr-lessons*

*Observed 2026-10-09 (python-dev)*
