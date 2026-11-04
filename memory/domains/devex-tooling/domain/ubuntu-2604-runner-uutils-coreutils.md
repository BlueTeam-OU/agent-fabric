---
role: "devex-tooling"
class: domain
topic: "ubuntu-2604-runner-uutils-coreutils"
description: "ubuntu-latest is Ubuntu 26.04 with uutils coreutils: a copied coreutils binary under another name fails (multicall picks by argv[0]), and date +%3N misprints milliseconds; time with EPOCHREALTIME, make stand-ins from bash"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 345646bea531f046
---

## ubuntu-latest is Ubuntu 26.04 with uutils coreutils: a copied coreutils binary under another name fails (multicall picks by argv[0]), and date +%3N misprints milliseconds; time with EPOCHREALTIME, make stand-ins from bash

GitHub's ubuntu-latest moved to Ubuntu 26.04 (seen 2026-10-24), whose coreutils is uutils
(0.10.0 then). Two required checks went red in two repositories within a day, with no commit
behind either:

- **Multicall by argv[0].** uutils is one binary that picks its utility from the name it was
  run under. A test that copies `sleep` (or any coreutils tool) to another name gets
  "unknown program" on every exec. gzapp's test_prune_testcontainers did this, and its probe
  hid the stderr behind a "noexec /tmp?" diagnosis that was wrong (gzapp #1162: the stand-ins
  became copies of bash).
- **`date +%s%3N` is wrong in the first tenth of each second.** %3N takes the first three
  digits of the *unpadded* nanoseconds (034705108 prints 347). A test's stopwatch misread a
  1 s deadline as 235–1871 ms; 11 of 150 runs failed (InterWeave #424 moved to bash
  `$EPOCHREALTIME`, 0 of 150).

**How to apply:** in a shell test, measure time with `$EPOCHREALTIME` (bash 5), never `date`
with %N. Make a stand-in executable a copy of bash or a script, never a renamed coreutils
binary. When a check goes red on many PRs at once, reproduce in an `ubuntu:26.04` container
(old red, new green) before trusting the check's own diagnosis. The general method is
[[same-source-red-read-the-floating-layer]]; the fold that a fix then needs is
[[gh-rerun-keeps-workflow-snapshot]].

*References: gh-rerun-keeps-workflow-snapshot, same-source-red-read-the-floating-layer*

*Observed 2026-10-25 (devex-tooling)*
