---
role: "rust-services-dev"
class: domain
topic: "pipefail-head-sigpipe"
description: "`cmd | head -1` under set -o pipefail fails intermittently and silently; use sed's q instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - d07dd906f297ed11
  - f53c2b326427bfad
---

## `cmd | head -1` under set -o pipefail fails intermittently and silently; use sed's q instead

Under `set -euo pipefail`, `x="$(sed -n 's/^p //p' f | head -1)"` fails whenever head
exits before the producer finishes writing: the producer gets SIGPIPE, the pipeline's status
is non-zero, the assignment fails and `set -e` ends the script with nothing on stderr. It is
timing-dependent (one parallel run in six failed in the case that taught it), so it passes
locally and flakes later.

**Why:** a live-check script and a fake launcher both carried the pattern; the replacement
passed 8 of 8 where the old form had failed.

**How to apply:** in any pipefail script, read the first match with one process that
quits itself — `sed -n '/^p /{s/^p //p;q}' f` — and add `|| true` only where an absent
file means "not yet". A producer that reads its whole input before writing (tr, od) is safe.

*Observed 2026-10-15 (rust-services-dev)*

## `cmd | head -1` under `set -euo pipefail` can end a shell script silently; quit inside the producer instead

Under `set -euo pipefail`, `x="$(sed -n 's/^pfx //p' file | head -1)"` fails at random: once `head` has its line and exits,
the producer gets SIGPIPE, the pipeline's status is non-zero, the assignment fails and `set -e` ends the script with no message
and an empty stderr. Measured: one parallel run in six failed this way; with the fix, eight of eight passed.

Fix: let the producer stop at the first match, e.g. `sed -n '/^pfx /{s/^pfx //p;q}' file`, adding `|| true` where an
unreadable file means "not yet". A filter that reads all of its input (`tr`, `tee`) is not at risk; only a reader that exits early is.

**Why:** the live-check scripts (spikes/live-account-switch/check-*.sh) are run once by the owner, and a silent early exit leaves
no summary and no reason. check-6 and check-8 carry the fixed form with a comment.

**How to apply:** in any new `pipefail` script, search for `| head` and `| grep -m` after a producer. A grep for these in xtask's
shell checks would be the executable form; that is a CI change for its owner, not a slice. [[claude-code-harness-driving]]

*References: claude-code-harness-driving*

*Observed 2026-10-15 (rust-services-dev)*
