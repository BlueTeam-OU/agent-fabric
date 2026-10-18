---
role: "rust-ui-dev"
class: domain
topic: "state-machine-signals-read-back"
description: "Before encoding a UI state machine someone else specified -- read every signal back live; unobservable ones are a finding with an observable substitute"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ab5ec572ff99b64
---

## Before encoding a UI state machine someone else specified -- read every signal back live; unobservable ones are a finding with an observable substitute

A state-machine contract written from the outside named transitions on signals the platform
never exposes; in one terminal-multiplexer contract three did:
- a child's exit code, when the host removes a pane on exit and keeps no code;
- a keypress consumed by the child process, which the controller never sees;
- "the program is in the pane's foreground", when sudo's use_pty moves the target session to
  its own pty (the pane's foreground group is the outer sudo; walk /proc/<pid>/stat ppid
  links from it instead).
Before building, read each transition's signal back on the live system; report each
unobservable one with what IS observable and a proposed reading. Also check the actions:
re-arming a pane by typing keys into a running program was refused in favour of acting only
when the controller sees its own bare shell.

*Observed 2026-10-15 (rust-ui-dev)*
