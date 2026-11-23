---
role: "python-dev"
class: domain
topic: "j203-setsid-escapes-group-kill"
description: "group-kill (start_new_session + killpg) misses a setsid'd descendant; walk parentage BEFORE any signal, note pids for the finally; #479"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0c1b7cd84b8f80d
---

## group-kill (start_new_session + killpg) misses a setsid'd descendant; walk parentage BEFORE any signal, note pids for the finally; #479

A site that spawns with start_new_session=True and ends the child with killpg leaves any descendant that called setsid running (tools_install.run_program, review_codex._end_group before #479). Fix: bounded.stop_tree (walks /proc by ppid) FIRST, then killpg KILL. A group TERM before the walk kills the parent and reparents the helper to init, out of the walk. Also snapshot bounded.descendants() before stop_tree and KILL them in the finally: a signal handler raising inside stop_tree's grace sleep skips its own per-pid KILL.

Test shape: `sh -c 'setsid sleep 300 & echo $! > pidfile; sleep 300'` (non-leader setsid execs in place, so $! is the sleeper); fake with `trap '' TERM; exec setsid sleep 300` for the interrupt-in-grace case. Patch bounded.STOP_GRACE_S, not a module copy.

**Why:** #479 (j203), found by reproducing on main with a marker/pid helper.
**How to apply:** any new spawn site with a timeout: use run_bounded/stop_tree, not killpg alone. Gap left: review_codex's snapshot loop has no test of its own. tests/run.sh full-suite lock can hold 2 h (exit 75): CI-green head was the arming evidence. [[bounded-subprocess-three-seams]]

*References: bounded-subprocess-three-seams*

*Observed 2026-11-04 (python-dev)*
