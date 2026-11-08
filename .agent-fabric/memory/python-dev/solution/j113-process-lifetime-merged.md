---
role: "python-dev"
class: solution
topic: "j113-process-lifetime-merged"
description: "j113 external review F06/F07/F11 merged as #477; SIGINT-hold-across-Popen, default_run on run_bounded, AGENT_FABRIC_LAUNCH_TMPDIR marker; review/arm traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 76a2b3d7567e9d3a
---

## j113 external review F06/F07/F11 merged as #477; SIGINT-hold-across-Popen, default_run on run_bounded, AGENT_FABRIC_LAUNCH_TMPDIR marker; review/arm traps

#477 merged 2026-11-04 (3 work, 2 fix, head e3dce9bc). F06: quiet() swaps a recording SIGINT handler in before Popen and raises it inside the cleanup try (skipped when SIGINT already ignored). F07: default_run = bounded.run_bounded (+ stop_tree on any BaseException, partial output kept on TimeoutExpired, `label=`). F11: AGENT_FABRIC_LAUNCH_TMPDIR marks the launcher's own default; only TMPDIR == marker == default_tmpdir counts as not-an-override.

**Why:** an invariant held at one spawn/entry point was lost at a sibling. Sibling spawn sites (review_codex probe, tools_install.run_program, trial_merge) were left to the requester's j602.

**How to apply:**
- A test that sends SIGINT after Popen cannot catch a defect in the handler-install window; wrap signal.signal to send it right after the handler goes in (review F4).
- A subprocess.run replacement with capture_output hangs on the base when a grandchild holds the pipe: reproduce the base with `timeout 20`, not a bare unittest run.
- Never `git checkout <file>` to undo a mutation when the real fix is uncommitted; copy the file first.
- Boundary PR under 8 work: ask the requester (a fabric-coordinator holder) for a REPLY with `AUTHORIZES: <repo>#<n>@<head8>`, then `fabric-pr arm --authorization <id>`; a test-only fix commit changes the head and needs its own re-review round.
- `fabric-pr post-review` must be the bare command with a literal path after `<`; write the report with the Write tool, not a chained heredoc.

*Anchors: `tools/fabric/langid_install.py::quiet`, `tools/fabric/control/upgrade.py::default_run`, `tools/fabric/launcher/session.py::settle_tmpdir`*

*Observed 2026-11-04 (python-dev)*
