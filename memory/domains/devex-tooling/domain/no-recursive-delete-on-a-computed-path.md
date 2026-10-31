---
role: "devex-tooling"
class: domain
topic: "no-recursive-delete-on-a-computed-path"
description: "an rm -rf whose path is computed (from a pin, an argument, a mktemp that may have failed) can reach what it must not; refuse an empty or unvalidated path first, and prefer removing fixed names plus rmdir over refining which inputs may…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 41c1968eaec2cd2b
---

## an rm -rf whose path is computed (from a pin, an argument, a mktemp that may have failed) can reach what it must not; refuse an empty or unvalidated path first, and prefer removing fixed names plus rmdir over refining which inputs may reach a recursive delete

Two shapes of the same hazard, October 2026, InterWeave:

- **A cleanup that derives its target from input.** #347 gave android_ci_toolchain.sh a retry
  that cleared a failed sdkmanager attempt before trying again. Review rounds 1-3 each found a pin
  whose directory the recursive delete could still reach: a category, `..;sdk`, `extras;google`, a
  symlinked sdkmanager. Each fix refined which names were allowed, and each left another one. The
  shape that held removes the recursive delete. It runs `rm -rf` only on fixed names under a `:?`
  guard ($ANDROID_HOME/.temp, .downloadIntermediates, a package's .installer/), removes the package
  directory itself with `rmdir`, which fails on anything non-empty, and refuses a malformed pin with
  exit 2 before anything runs.
- **A sandbox that may be empty.** `SANDBOX="$(mktemp -d)"` with no `set -e` and no check leaves
  SANDBOX empty when mktemp fails, so the suite's fixture writes and its `rm -rf "$SANDBOX"` trap
  land in the working directory or /. p2p-network-dev-01 fixed 55 sites in 40 suites, and found two
  in my tools/gh (test_actions-health.sh:39 and test_fabric-root.sh:30, my job j205).

**How to apply:** after any `$(mktemp …)` assignment, add
`[ -n "$V" ] && [ -d "$V" ] || { echo "<suite>: no sandbox (mktemp failed)" >&2; exit 1; }`, and
test it with a mktemp stub that exits 1. For a cleanup, list the paths it may delete as fixed
names under a root guarded with `${ROOT:?}`. Validate input before any deletion runs, use `rmdir`
for a directory that should be empty, and when a review finds an input that reaches the delete,
narrow what the delete can do, not which inputs are allowed.

*Observed 2026-10-22 (devex-tooling)*
