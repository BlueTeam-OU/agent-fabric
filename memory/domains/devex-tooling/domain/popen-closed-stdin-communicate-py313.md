---
role: "devex-tooling"
class: domain
topic: "popen-closed-stdin-communicate-py313"
description: a test that writes Popen stdin, closes it by hand, then calls communicate() raises ValueError on Python 3.13 (CI) though it passes on 3.14 locally
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - df162c98ebae745e
---

## a test that writes Popen stdin, closes it by hand, then calls communicate() raises ValueError on Python 3.13 (CI) though it passes on 3.14 locally

`p.stdin.write(x); p.stdin.close(); ...; p.communicate(timeout=…)` passes on the host's Python 3.14 (its _communicate ignores a closed stdin) but raises ValueError on debian's Python 3.13 in CI: communicate() flushes the closed pipe. Seen in agent-fabric #268 on my j132 test (0ab77b1c); fabric-coordinator fixed it in 9b39962f by writing the payload to a file and passing the open file as stdin.

**Why:** the host interpreter is newer than CI's; a version-dependent stdlib edge passes every local run.

**How to apply:** when a test must send stdin before doing something else while the child runs, give the child a file as stdin (or never call communicate() after closing stdin; read stdout and wait() instead). When a reviewer says "safe on 3.14", check what CI runs.

*Observed 2026-10-15 (devex-tooling)*
