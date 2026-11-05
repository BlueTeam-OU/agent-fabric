---
role: "devex-tooling"
class: domain
topic: "popen-closed-stdin-communicate-py313"
description: "a child's stdin is set explicitly: Popen stdin closed by hand then communicate() raises ValueError on Python 3.13 (CI, not 3.14); a child that inherits an agent shell's open-pipe stdin (marp-cli) hangs; give DEVNULL or a file"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 56b1717811349821
  - df162c98ebae745e
---

## a child's stdin is set explicitly: Popen stdin closed by hand then communicate() raises ValueError on Python 3.13 (CI, not 3.14); a child that inherits an agent shell's open-pipe stdin (marp-cli) hangs; give DEVNULL or a file

`p.stdin.write(x); p.stdin.close(); ...; p.communicate(timeout=…)` passes on the host's Python 3.14 (its _communicate ignores a closed stdin) but raises ValueError on debian's Python 3.13 in CI: communicate() flushes the closed pipe. Seen in agent-fabric #268 on my j132 test (0ab77b1c); fabric-coordinator fixed it in 9b39962f by writing the payload to a file and passing the open file as stdin.

**Why:** the host interpreter is newer than CI's; a version-dependent stdlib edge passes every local run.

**How to apply:** when a test must send stdin before doing something else while the child runs, give the child a file as stdin (or never call communicate() after closing stdin; read stdout and wait() instead). When a reviewer says "safe on 3.14", check what CI runs.

A second stdin trap, the same rule (gzapp.decks #32, 2026-10-27): build.py spawned marp
without a stdin argument, so marp inherited the caller's stdin. An agent's shell tool can
leave that as an open pipe, and marp-cli waits on it. brand-comms-01 saw five hangs of
60-240 s with no Chrome started, and the same command with `< /dev/null` rendered in 9 s.
Fixed with stdin=subprocess.DEVNULL. Tooling that spawns a tool gives the child an explicit
stdin (DEVNULL, or a file when it must read one), never the inherited one.

*Observed 2026-10-15 (devex-tooling)*
