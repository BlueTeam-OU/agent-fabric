---
role: "python-dev"
class: workflow
topic: "j218-finding-1-check-flipped"
description: "j218 flipped the W2-B0 finding 1 transport check; for/ branch folded by the coordinator onto #532; mutation line"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23f2d35984c2212a
---

## j218 flipped the W2-B0 finding 1 transport check; for/ branch folded by the coordinator onto #532; mutation line

j218: tests/test_gzcoord_message_transport.py finding 1 check now asserts no relay-down/back line for an --until-delivery watch that rides out a drop. Mutation: guard `if not until_delivery:` before the watch.relay-down print in tools/fabric/gzcoord/inbox.py -> `if True:`. Delivered as for/ branch 3ef18ac6, folded as 3f7065b1 on #532.

**Why:** the request's base commit was already on main, and the finding 2 xfail was not on that base, so an acceptance line can name something absent; say so in the REPLY rather than guess.
**How to apply:** check each acceptance clause against the base before running; a mutation run on a copy of the source, restored by cp, leaves the tree clean. A lint+commit call can exceed 120 s and move to the background; read git log, do not re-commit.

*Anchors: `tools/fabric/gzcoord/inbox.py::until_delivery`, `tests/test_gzcoord_message_transport.py::watch.relay-down`*

*Observed 2026-11-09 (python-dev)*
