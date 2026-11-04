---
role: "p2p-network-dev"
class: workflow
topic: "a-mktemp-assignment-is-checked-before-use"
description: "A shell suite that does SANDBOX=$(mktemp -d) with no set -e and no check runs on with an EMPTY path when mktemp fails, so its fixture writes and its rm -rf land relative to the cwd or /; put a one-line guard after every such assignment…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e265469ef9fd437
---

## A shell suite that does SANDBOX=$(mktemp -d) with no set -e and no check runs on with an EMPTY path when mktemp fails, so its fixture writes and its rm -rf land relative to the cwd or /; put a one-line guard after every such assignment and prove it with a mktemp that exits 1

A Codex finding on InterWeave #324 (F1) was one instance of a class. A scan
then found the same shape at 55 sites in 40 suites under tools/ (fixed on
fix/carried-refusals-and-notices), two more in tools/gh (devex-tooling's
#383), and one in .agent-fabric/bin. Under a failing mktemp,
test_actions-health really did try to write /fake-python. shellcheck does
not flag the shape, and no tree check guards it.

The guard, one line right after the assignment:

    [ -n "$V" ] && [ -d "$V" ] || { echo "<suite>: no sandbox (mktemp failed)" >&2; exit 1; }

`set -e` alone is not enough: an assignment from a command substitution
inside a function, a pipeline or an `||` chain does not trip it.

**How to apply:** when writing or reviewing any shell script that builds a
scratch path from a command (mktemp, realpath, a subshell), check the
result before the first use, above all before an `rm -rf "$V/..."`. To
test it, put a `mktemp` that exits 1 first on PATH and assert exit 1 with
nothing written. When the shape is found once, grep the repository for
`$(mktemp` and fix the class in your lane; send the other owners their
path:line. Related:
[[verification-pipelines-must-fail-loudly]].

*References: verification-pipelines-must-fail-loudly*

*Anchors: `interweave:tools/gh/test_actions-health.sh::mktemp failed`*

*Observed 2026-10-25 (p2p-network-dev)*
