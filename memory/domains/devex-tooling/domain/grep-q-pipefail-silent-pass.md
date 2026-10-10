---
role: "devex-tooling"
class: domain
topic: "grep-q-pipefail-silent-pass"
description: "In a guard under set -o pipefail, never end a pipe in grep -q -- its early exit SIGPIPEs the writer and a match reads as a miss"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 24fb427fe468ce57
---

## In a guard under set -o pipefail, never end a pipe in grep -q -- its early exit SIGPIPEs the writer and a match reads as a miss

`producer | grep -q PATTERN || continue` under `set -o pipefail`: grep -q exits at the
first match, the producer is killed by SIGPIPE (141), and the pipeline's status is 141,
so a MATCH reads as no match. Size-dependent: InterWeave's check_rustc_pin.sh (#182,
e3e2d23f) skipped a config setting `build.rustc` 24/300 times at 4.6 KB and 20/20 at
136 KB -- a silent pass in a fail-closed guard; every small test case passed. Fixed in
3f9ec006 by filtering into a variable, then `grep -q PAT <<<"$var"`.

How to apply: in any guard with pipefail, filter into a variable first (or drop -q and
send output to /dev/null), and give the test a match ahead of >128 KiB of input; a
pipe ending in `head -1` is only safe where the status is not read. A shell function
wrapping grep (ugrep) can hide this in an interactive shell -- reproduce with
/usr/bin/grep. Related: [[ci-command-line-is-read-by-guards]].

*References: ci-command-line-is-read-by-guards*

*Observed 2026-10-04 (devex-tooling)*
