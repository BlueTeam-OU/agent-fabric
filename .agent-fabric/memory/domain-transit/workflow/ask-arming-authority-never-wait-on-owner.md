---
role: "domain-transit"
class: workflow
topic: "ask-arming-authority-never-wait-on-owner"
description: a PR that needs a word to arm — REQUEST the arming authority by GZCoord and take the next job; never stop asking the owner
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a00068f07a420dd
---

## a PR that needs a word to arm — REQUEST the arming authority by GZCoord and take the next job; never stop asking the owner

The owner's rule, broadcast by fabric-coordinator 2026-11-09 (INFO 01a1c1dc-793e-719a-9f20-b4cecc041a26): when arming needs a word (below the work-commit minimum, a security-boundary path, a finding to defer), never end the turn asking the owner. Send a REQUEST to the login that `fabric-pr arm --dry-run` names as the arming authority (fabric-coordinator in agent-fabric, architect-cto in a project), naming the PR, its head and its counts; then `fabric-jobs next` while the answer comes through the inbox watch. The AUTHORIZES header of that reply is what arm reads.

**Why:** sessions sat idle at the prompt waiting on the owner for a word that the arming authority can give.
**How to apply:** only money, accounts, a new host or accepting an ADR still go to the owner. The owner's-word path in [[arm-owner-word-ignores-authorization]] is now the exception, used only when the owner gives the word unprompted.

*References: arm-owner-word-ignores-authorization*

*Observed 2026-11-09 (domain-transit)*
