---
role: "python-dev"
class: workflow
topic: "review-report-post-extract-from-transcript"
description: "auto-mode refuses only a retyped review report; post the reviewer's verbatim SubagentHandback text myself, ask the owner only after a quoted refusal"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 836f2b71d69add20
---

## auto-mode refuses only a retyped review report; post the reviewer's verbatim SubagentHandback text myself, ask the owner only after a quoted refusal

A review subagent's report reaches the session only as message text. Writing it
to a file by hand (even condensed) and running `fabric-pr post-review` was
refused by the auto-mode classifier as self-approval (j72, #418, 2026-10-28).

**Why:** my retyped file is not the reviewer's text; posting it passes my words
off as the independent review.

**How to apply:** try it yourself first. policies/auto-mode.json:20 allows
posting the review class's report *as it returned*; only a report I wrote or
edited is refused. The reviewer's final text is the `input.message` of the last
`SubagentHandback` tool_use in `tasks/<agentId>.output` (JSONL): extract it
verbatim to the scratchpad, then run, as bare commands, `fabric-pr post-review
<pr> --model fable < file`, `fabric-review save <pr> <round> < file`, `fabric-pr
gate <pr>`. Hand the owner a command only after my own session's refusal, quoted
(coordinator, 2026-10-30; in j73 I handed over in advance from this memory and
nothing had been refused). Keep an owner command short (a one-line path).
A re-review brief for a PR whose branch is behind origin/main needs origin/main
merged first and the range pinned as full shas (`HEAD` is refused by
`fabric-review next`). A review of head A does not cover fix commit B: the
re-review of the fix range is posted the same way. `fabric-pr arm` on the
owner's word works once the head is covered, even under the security-boundary
and 8-commit minimums.

*Anchors: `tools/fabric/github/post_review.py::REVIEW_MARKER`*

*Observed 2026-10-30 (python-dev)*
