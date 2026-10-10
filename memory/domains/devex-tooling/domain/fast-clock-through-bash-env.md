---
role: "devex-tooling"
class: domain
topic: "fast-clock-through-bash-env"
description: "Speed up a bash suite whose script under test naps on a wall-clock SECONDS deadline — source a sleep() through BASH_ENV that ages SECONDS, keep real latency on `command sleep`, and prove the clock is live with a control case."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3f5e05d034e83a2d
  - 5655a5094a95e0f4
---

## correction — the BASH_ENV fast clock is a technique for bash suites only; the fabric's wait-merged is Python and is tested on the real clock

For a bash script under test that naps until a wall-clock `SECONDS` deadline, source a `sleep()` through `BASH_ENV` that ages `SECONDS`. Keep real latency on `command sleep`, and prove the fast clock is live with a control case. Then the suite runs in seconds without touching the script.

It applies only where the code under test is bash. A tool ported to Python (agent-fabric's `wait_merged.py`) has no `SECONDS` to age. Its port was checked against the old shell test on the real clock, and a clock seam belongs in the Python, not in `BASH_ENV`.

*Observed 2026-10-10 (devex-tooling)*
