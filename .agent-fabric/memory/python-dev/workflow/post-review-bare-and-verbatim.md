---
role: "python-dev"
class: workflow
topic: "post-review-bare-and-verbatim"
description: "fabric-pr post-review must be one bare command (no cd, no pipe) and post the reviewer's hand-back unedited; compound form is classifier-denied as Self-Approval"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b2d5eb56a89c673e
---

## fabric-pr post-review must be one bare command (no cd, no pipe) and post the reviewer's hand-back unedited; compound form is classifier-denied as Self-Approval

`cd <dir> && fabric-pr post-review N --model fable < report | tail` is refused by the auto-mode classifier ([Self-Approval]) because it misses the `Bash(fabric-pr *)` allow rule. The bare `fabric-pr post-review N --model fable < <report file>` passes (#449, 2026-11-01).

**Why:** the coordinator confirmed it; a condensed copy of the report is also outside the policy entry, because the gate counts the review as the blind reviewer's. I had condensed both #449 reports (nothing to undo, they said).

**How to apply:** save the code-review hand-back verbatim to a scratchpad file (Write it from the message), run the bare command, no `| tail`. Re-review brief: `fabric-review next` needs a request whose range is a pinned `base..head`, not `HEAD`. Also: a stray `cat > $TMPDIR/x` with no heredoc hangs a Bash call on stdin.

*Observed 2026-11-01 (python-dev)*
