---
role: "devex-tooling"
class: domain
topic: "cargo-tree-resolved-features-format"
description: "to check which features a build resolves, use cargo tree -f '{p}|{f}', not -e features (misses a root's own features)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - cefa8a8eba1f0bcc
---

## to check which features a build resolves, use cargo tree -f '{p}|{f}', not -e features (misses a root's own features)

`cargo tree -e features` shows a feature only as an edge from a dependent, so a
feature enabled on a ROOT package (`-p x --features f`) never appears — measured
2026-10-30 on interweave-transport-composition: `--features test-hooks` gave no
`test-hooks` line. `cargo tree -e normal --prefix none -f '{p}|{f}'` prints each
package's resolved feature set, roots included; `{p}` ends in "(path)", so split
on the LAST `|`. Several `-p` in one call unify features as one build does.
`--target aarch64-linux-android` works without that target installed (passed in
InterWeave CI tree checks, PR #514). Guard: tools/checks/check_shipped_test_hooks.sh.
Reading release command lines for it took four review rounds of regex gaps
(see [[shell-reader-allow-list-not-parser]]): anchor whole lines, exempt only the
exact line read, and count writers of what you read.

*References: shell-reader-allow-list-not-parser*

*Observed 2026-10-30 (devex-tooling)*
