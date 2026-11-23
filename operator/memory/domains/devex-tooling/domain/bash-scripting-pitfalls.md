---
role: "devex-tooling"
class: domain
description: "bash's command_not_found_handle runs in a subshell (5.3+) — a counter-based self-test guard built on it is silently vacuous"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-74e1ddd4096a45ce"
    host: "develop-qzapp"
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 08a97682a41fe389
  - 1ee2629683907fec
  - 3d59d3dd4093d299
  - 5b009633751813b8
  - a2fa0085e14d2d48
  - abd6cb691580c966
  - d779c6c5209a7ff3
  - e88d5e3a257dd3dc
  - ecc6f72637971603
  - ef899294d48a5df5
  - f38fb002a7ae6717
---

## Two recurring bash pitfalls: arithmetic-context injection and hardcoded --help ranges

First: bash's `$(( expr ))` arithmetic context re-evaluates a variable's string content as an expression, including command substitution reachable via array-subscript-like syntax — so piping an unvalidated CLI flag straight into `$(( LIMIT * 20 ))` is a command-injection vector (a payload like `-n 'x[$(touch pwned)]'` executes). Validate any "numeric" argument against a strict `^[1-9][0-9]*$`-style regex BEFORE it reaches arithmetic, not after. Second: implementing `--help` in a self-referential script via a hardcoded line range (e.g. `sed -n '3,36p' "$0"`) silently truncates as soon as anything is added above that range — new flags documented further down just stop appearing in `--help` output with no error. Use marker comments instead (e.g. `# >>> help` / `# <<< help`, extracted with a range-matching `sed`), which stay correct regardless of later edits.

## bash's command_not_found_handle runs in a subshell (5.3+) — a counter-based self-test guard built on it is silently vacuous

A third bash gotcha to add alongside the existing two (arithmetic-context injection, hardcoded --help ranges): bash executes `command_not_found_handle` in a SUBSHELL, so any shell-variable mutation inside it (e.g. `failures=$((failures+1))`) is discarded the instant that subshell exits — the handler's own output (an error message, a printed '✗') is visible, but the parent test-suite script never sees the failure and reports 'all assertions passed' with exit 0 regardless. This repo shipped exactly that bug across five `tools/gh/test_*.sh` self-test guards meant to catch a typo'd assertion-helper name (e.g. calling `assert_not_contains` where the file only defines `assert_lacks`) — the guard fired, printed the right diagnostic, and the suite still exited 0. The fix is a `mktemp` marker file: the handler appends to it, and the suite checks after all tests run whether the marker file is non-empty, because a file written inside the subshell survives it while a variable does not. Separately, a mutation test verifying such a guard by copying the test script to `/tmp` before injecting a fake call can produce a false 'guard did not work' result: if the guard resolves its own `UNDER_TEST` path relative to the script's own location, running the copy from `/tmp` makes that resolution fail and the suite aborts before ever reaching the injected typo — always mutation-test a self-test guard in place, not from a copy elsewhere.
