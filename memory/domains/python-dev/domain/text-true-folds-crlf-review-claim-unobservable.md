---
role: "python-dev"
class: domain
topic: "text-true-folds-crlf-review-claim-unobservable"
description: "subprocess text=True turns CRLF into LF, so a \"split before replace \\r\" review finding on gh output is not observable; non-exec fake needs PATH without a later real binary"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ecb146418de089c
---

## subprocess text=True turns CRLF into LF, so a "split before replace \r" review finding on gh output is not observable; non-exec fake needs PATH without a later real binary

A review finding that says "CRLF defeats this split" on output read through `subprocess.run(..., text=True)` is not reachable: universal newlines already folded `\r\n` to `\n`. Test it before building a test around it; a mutation that swaps the order survives, so say so and pin the real invariant (the header/body split) with a mutation that is caught. #281 round 1 F3 (github_signing_key.token_scopes, 2026-10-16).

**Why:** I almost reported a caught mutation that was never planted; the first sed did not apply.
**How to apply:** after planting a mutation, `git diff` the file and confirm the changed line before reading the suite's rc.

A fake non-executable `gh` (chmod 644) only raises PermissionError when no runnable `gh` is later on PATH: set PATH to the fake's directory alone for that case. See [[mutation-run-read-rc-not-fail-count]].

*References: mutation-run-read-rc-not-fail-count*

*Observed 2026-10-16 (python-dev)*
