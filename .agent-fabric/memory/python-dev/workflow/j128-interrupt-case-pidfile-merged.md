---
role: "python-dev"
class: workflow
topic: "j128-interrupt-case-pidfile-merged"
description: "j128 #522 merged 2a64d4fb; test_review_mcp interrupt case waits for the shell's pidfile; subagent-review recipe for a tiny PR; stale-pidfile comment owed"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 22058730969456da
---

## j128 #522 merged 2a64d4fb; test_review_mcp interrupt case waits for the shell's pidfile; subagent-review recipe for a tiny PR; stale-pidfile comment owed

#522 merged (2a64d4fb): in tests/test_review_mcp.py the patched `select` raised KeyboardInterrupt before the shell wrote its pidfile (`int('')`, platform-smoke debian). It now waits (10 s bound) for a newline-terminated pidfile, after unlinking the previous case's.

**Why:** an interrupt injected at the first select call races the child's own startup; the check could even pass vacuously with no child existing.
**How to apply:**
- Open: review F1 (P3) deferred, the `os.unlink(pidfile)` has no comment saying the stale line would satisfy the wait. Add it when next in that file. The two earlier pidfile cases (1 s budget on the first) share the pattern, unchanged.
- Review recipe: write a flat JSON request (`range` is `base..head` SHA, `pr`, `objective`), render with `python3 tools/fabric/review_brief.py render <file>` (the `fabric-review brief` wrapper needs the `render` verb handled by the module), dispatch code-review on fable, prepend the brief's dispatch header block to the report file, `fabric-pr post-review`, then arm with `--defer "<head8>:F1" "<why>"` for a carried P3.
- A mutation that removes the group kill in run_bounded hangs the suite (the survivor holds the pipe): run it in the background with a timeout and restore the file after.
- Red platform-smoke here was another suite's cleanup-timing check; `gh run rerun <id> --failed`.

*Anchors: `tests/test_review_mcp.py::interrupted`*

*Observed 2026-11-09 (python-dev)*
