---
role: "fabric-coordinator"
class: workflow
topic: "request-verify-premise-before-sending"
description: Before a REQUEST, INFO or broadcast, check its premises on origin/main (the code, caller, branch and field it names exist; search by purpose, not file name) and run each step it asks for in my own session; carry content, never a pointer…
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1ae437ddcc05bce1
---

## Before a REQUEST, INFO or broadcast, check its premises on origin/main (the code, caller, branch and field it names exist; search by purpose, not file name) and run each step it asks for in my own session; carry content, never a pointer the recipient cannot read

Recipients caught a false premise in my messages again and again: a branch "not on origin", a field "NOT in any hook payload", nothing to wire a hint into, a module or oracle that "already existed on main" because I searched by the wrong file name, a grep hit taken for a read. Broadcast steps failed at the recipient too: "a job's notes" that fabric-jobs does not have, a `git worktree remove` that auto mode refused, an "install it yourself" that conflicted with the session-start rule. A REQUEST pointing at `fabric-plan show` reached roles that cannot read plans.

W43 added six of my own corrections. "Fails on main too" was never run. "Arm on the claude review" went out when `fabric-pr gate` showed no claude review. A record draft missed the owner's earlier answers. An ADR path was wrong. A disk broadcast described the sweep's keep rule from memory, not from `--help`. "No word needed" went to a security-boundary PR that `arm --dry-run` refused. Within two hours I told one holder that agent-fabric's count rule was 1 and another that it was 8. `policies/arming.json` says 8. Each one cost the recipient a round.

**Why:** a wrong premise stalls the recipient, and a bulk broadcast stalls many at once.
**How to apply:** before composing, read the named code on origin/main, `git ls-remote` any branch I cite, grep by docstring and purpose, and paste plan content into the message. Run every step of an instruction myself first. State an arming minimum, or whether a word is needed, only from `fabric-pr arm <n> --dry-run` on that head, and a command's behaviour only from its `--help`. Related: [[find-oracle-by-docstring]], [[request-check-authority-fence]], [[owner-commands-one-line]].

*References: find-oracle-by-docstring, owner-commands-one-line, request-check-authority-fence*

*Observed 2026-10-25 (fabric-coordinator)*
