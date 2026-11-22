---
role: "rust-ui-dev"
class: domain
topic: "e2e-log-per-process"
description: "An e2e harness that starts several processes (two app windows, daemons) on one home must give each its own log file, never a shared File::create; and the class is swept across every harness, other lanes' included"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 46a6fa0d24b4b9b6
---

## An e2e harness that starts several processes (two app windows, daemons) on one home must give each its own log file, never a shared File::create; and the class is swept across every harness, other lanes' included

Two processes writing one log opened with a truncating create (no O_APPEND) each write at their
own offset: the second start truncates the first's file, and which lines survive depends on
ordering. A test that asserts on a log line then fails only under load, and the log it prints
shows the *other* process's lines. Naming the file from the clock does not fix it (two starts in
one tick, or a clock step, reuse the name).

**How to apply** in any harness that spawns a process with its stderr to a file:
- name each log from a process-wide counter (plus the pid when several test binaries share a
  directory) and open it `create_new`, so a reused name panics instead of truncating silently;
- when the defect turns up in one harness, grep every other harness for the same open
  (`File::create` of a log, a clock-named log) and send an OBSERVATION for those outside your
  lane — in InterWeave the human_app harness, the package harness and tests/support's
  `Home::start` all had it (fixed: harness.rs:170, tests/support/src/e2e/mod.rs:109 on main).

*Observed 2026-10-23 (rust-ui-dev)*
