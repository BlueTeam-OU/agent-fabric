---
role: "python-dev"
class: solution
topic: "j125-process-lifetime-module-pr514"
description: "j125 W1-A: PR 514 process.py one owner of process lifetime; what waits on coordinator, fixture and review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 19669561e4230f8e
---

## j125 W1-A: PR 514 process.py one owner of process lifetime; what waits on coordinator, fixture and review traps

#514 MERGED 2026-11-09 at head a8bfe71a (16 work, 2 fix); the coordinator folds for/user/j125-process-spawns, the allowlist and lint wiring into its #515. Before merge it waited on: policies/process-spawns.json (moveto only), arm.json boundary regex `process` (arm.py import closure reaches process.py via review_mcp/runner; test_arm_fabric_config and CI ci-ok are red until then), mechanisms.json owner, lint wiring, folding for/user/j125-process-spawns (freshness hook). moveto.py declined: installed alone on hosts.

**Why:** the commit hook refuses policies/ and projects/ even on a for/user branch (outside the python-dev entry): hand the content in the REPLY, not a branch.

**How to apply:**
- A coordinator commit onto my branch changes the head: the suite and a re-review of that range are mine to run again; a boundary change needs a boundary.changes entry (lint arm_boundary_findings), which the coordinator's first commit lacked (F5). The count rule (1 work in agent-fabric) armed it, so the AUTHORIZES was not read.
- A new sibling import in a tools/fabric module breaks every test fixture that copies a file list: grep tests for the module name (test_run tree(), test_launch, test_new_agent_cli, test_account_drift, cpu-shim PAYLOAD) and run the full suite; a standalone-installed file (lease.py via PAYLOAD, moveto.py) cannot take a new import silently.
- Launcher parts load siblings by path (base.py `_load`), never `import`.
- bounded.py is a module-class shim: names process.py's functions read from their own globals (STOP_GRACE_S, stop_tree, descendants) must be forwarded on write or old test patches stop applying.
- A held SIGINT is re-delivered with signal.raise_signal after the handler is restored, so a caller's own handler (review_codex) decides.
- Mutation runs: run each test in its own session and killpg on timeout, else a mutated lease leaves a holder; sweep is per-site (default off); a SIGKILL'd member still reads alive for a moment, so wait before asserting alive.
- Waiter loops: `pgrep -f <name>` matches the waiter itself; poll /proc/<pid> instead.

*Anchors: `tools/fabric/process.py::group`, `tools/fabric/process_spawns.py::scan`, `tools/fabric/provisioning/bounded.py::_Shim`*

*Observed 2026-11-08 (python-dev)*
