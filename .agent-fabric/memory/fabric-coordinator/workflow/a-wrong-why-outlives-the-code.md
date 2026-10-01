---
role: "fabric-coordinator"
class: workflow
topic: "a-wrong-why-outlives-the-code"
description: When deferring work, record the cost you measured — never a blocker you inferred from your own failed attempt
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 5a27d4e1b545f303
  - ec23554e4b3bf3d9
---

## When deferring work, record the cost you measured — never a blocker you inferred from your own failed attempt

On 2026-09-23 I tried to extend `agent-dispatch-guard.sh`, referenced a
`$INPUT` variable that did not exist, concluded the change "means
buffering the hook's stdin", reverted, and wrote that blocker into a
comment as the reason for deferring. The re-review disproved it from the
guard's own code: it already builds whole maps in shell before `jq` runs
and passes them as `--argjson`, so nothing had to read the call first.
The real fix was fifteen lines.

**Why:** a deferral's comment is the one thing a later session will not
re-derive — it reads "this was considered and is hard" and moves on. A
blocker invented from a botched attempt makes the work look impossible
forever. `agent-fabric ADR-015 (docs/adr/ADR-015-code-is-memory.md)` asks a comment for the *why*
precisely because the why is unrecoverable from the code.

**How to apply:** when deferring, state the cost you actually measured
("five extra file reads per dispatch") or the scope decision ("out of
this PR"), never a mechanism you did not verify. If the reason is "my
attempt failed and I did not find out why", write *that* — it is true and
it invites the next session to look. And before recording any blocker,
re-read the thing you claim blocks you.

Related: [[guard-must-catch-the-shape-it-replaced]], [[blind-review-loop]].

*References: blind-review-loop, guard-must-catch-the-shape-it-replaced*

*Observed 2026-09-23 (fabric-coordinator)*
