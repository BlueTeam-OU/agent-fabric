---
role: "python-dev"
class: solution
topic: "moveto-ssh-parent-terminal-reset-j103"
description: "j103 moveto stays ssh's parent and resets terminal modes; how the pty test and mutations were done"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ec42f093a9d3df2d
---

## j103 moveto stays ssh's parent and resets terminal modes; how the pty test and mutations were done

runtime/provisioning/moveto/moveto.py `run_ssh` replaced the execvp of ssh (commits b35cc1ae, 73d8c2c8 on the #447 branch): Popen with restore_signals=False after setting SIGPIPE, forwards HUP/TERM/INT, writes TERMINAL_RESET to fd 1 only if a tty, returns ssh's status (128+n on signal). Tests in tests/test_moveto.py use pty.openpty as moveto's stdout and a fake ssh on PATH; expected sequences are spelt out in the test, not imported. Live deck read-back was not done by this login (no deck pane/pinned sshd) — left to the coordinator.

**Why:** a remote Claude Code sets kitty/mouse modes the deck's hang-up never clears.
**How to apply:** push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`; a check piped into && commit is blocked by a hook — log to a file, read rc.

*Anchors: `runtime/provisioning/moveto/moveto.py::run_ssh`, `runtime/provisioning/moveto/moveto.py::TERMINAL_RESET`*

*Observed 2026-11-01 (python-dev)*
