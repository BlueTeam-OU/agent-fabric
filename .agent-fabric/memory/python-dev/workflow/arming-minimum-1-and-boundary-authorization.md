---
role: "python-dev"
class: workflow
topic: "arming-minimum-1-and-boundary-authorization"
description: "agent-fabric arms at 1 work commit since 2026-10-19; tests of guards are a security boundary and need the coordinator's AUTHORIZES id"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2f7f3041a219cccf
---

## agent-fabric arms at 1 work commit since 2026-10-19; tests of guards are a security boundary and need the coordinator's AUTHORIZES id

Since agent-fabric-settings#9 (2026-10-19) agent-fabric's arming minimum is 1 work commit; read `fabric-pr arm <n> --dry-run`, never a number from memory, and do not ask the owner for a word it does not ask for.
Even so, `fabric-pr arm` refused #320 (tests/test_*_guard.py only) as a security-boundary change under 8: the guards' own test files match the boundary list. The way: send fabric-coordinator a REPLY asking for `AUTHORIZES: <owner/repo>#<n>@<head8>`; its DECISION carries that line; arm with `--authorization <message-id>` and a basis. The word covers that head only, so every fix after it needs a new one.
**Why:** a blind re-review of a fix range needs `card_base` (full sha the default branch holds) and `previous_findings` as a file path, not text.
**How to apply:** open the PR, post the review, send the AUTHORIZES request in the same turn as the green review, and carry docstring P3s by name rather than move a reviewed head. See [[arm-under-8-boundary-needs-owners-word-phrase]].

*References: arm-under-8-boundary-needs-owners-word-phrase*

*Observed 2026-10-19 (python-dev)*
