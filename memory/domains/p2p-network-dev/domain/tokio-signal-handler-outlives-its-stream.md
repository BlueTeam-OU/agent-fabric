---
role: "p2p-network-dev"
class: domain
topic: "tokio-signal-handler-outlives-its-stream"
description: "tokio::signal::unix::signal installs a process-wide OS handler that stays after the Signal stream is dropped; a mutation that drops the stream removes nothing"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 2e98e3a0081c346f
---

## tokio::signal::unix::signal installs a process-wide OS handler that stays after the Signal stream is dropped; a mutation that drops the stream removes nothing

`tokio::signal::unix::signal(kind)` installs an OS-level handler through signal-hook-registry the first time a kind is registered, and dropping the returned `Signal` does NOT uninstall it. For the rest of the process, that signal no longer takes its default action.

Seen in transportctl's phrase input (Stage 13 B5, 2026-10-01). `rpassword` answers Ctrl-C with `raise(SIGINT)` before restoring termios, so the handler is what keeps the terminal from being left with echo off. A mutation that "removed" the handler by dropping the stream before the read still passed the Ctrl-C test. Only skipping the registration altogether made it fail (`exit=130`, `stty` showing `-echo`).

**Why:** a mutation that only appears to remove the mechanism proves nothing about the test. Neither does a comment saying the handler is "for the read only".

**How to apply:** to turn a tokio signal handler off in a mutation, never register it. Don't describe a tokio handler as scoped to a block.

*Observed 2026-10-01 (p2p-network-dev)*
