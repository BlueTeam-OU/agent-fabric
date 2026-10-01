---
role: "fabric-coordinator"
class: workflow
topic: "branch-name-four-segments"
description: "Name fabric branches <host>/<login>/<type>/<what>; a three-segment name reads as \"names no session\" to pr-reply.sh and pr-sessions.sh"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee23836478a9fb40
---

## Name fabric branches <host>/<login>/<type>/<what>; a three-segment name reads as "names no session" to pr-reply.sh and pr-sessions.sh

Name every branch `<host>/<login>/<type>/<what>`, four segments (e.g.
`develop-qzapp/user/fix/followups`). My agent-fabric branches had three
(`develop-qzapp/user/followups`); on #56 `runtime/github/pr-reply.sh`
(`branch_names_a_session`, ≥4 segments) read the PR as unowned and left
every answered thread open until resolved by hand.

**Why:** ownership is the branch prefix, and the tools only recognise the
four-segment shape; a wrong "not a session" flips pr-reply to leave-open.

**How to apply:** branch off origin/main with a type segment (fix, feat,
docs, drain…). A remote branch of the same name left from an earlier PR
is not overwritten (that is a force push); pick a new name.

*Observed 2026-09-28 (fabric-coordinator)*
