---
role: "devex-tooling"
class: domain
topic: "ubuntu-26-04-coreutils-is-multicall"
description: "ubuntu-latest became ubuntu-26.04 (~2026-10-24); its coreutils is uutils, so a coreutils binary copied or symlinked under another name will not run"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 01ba862ad66f3b5b
---

## ubuntu-latest became ubuntu-26.04 (~2026-10-24); its coreutils is uutils, so a coreutils binary copied or symlinked under another name will not run

On ubuntu-26.04 (ubuntu-latest from about 2026-10-24 22:47Z) `/usr/bin/sleep` and the
other coreutils are links into one uutils multicall binary, which picks its utility from
argv[0]. A copy named `exec-probe` fails with "coreutils: unknown program", and a symlink
under another name fails with "Security violation: Requested utility … does not match
executable name". Any test that runs a coreutils binary under a fake process name breaks.
Use a copy of `$BASH` (`-c 'read -t N -u 9' 9<>fifo` so no child is forked) instead.
A probe that throws away stderr will guess the wrong cause (here it blamed noexec).
gzapp #1162 (j220), verified in a docker.io/library/ubuntu:26.04 container.

*Observed 2026-10-25 (devex-tooling)*
