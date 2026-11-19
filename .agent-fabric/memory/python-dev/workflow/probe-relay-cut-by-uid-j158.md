---
role: "python-dev"
class: workflow
topic: "probe-relay-cut-by-uid-j158"
description: "j158: relay made unreachable for one scratch login by an nft uid rule; root is the owner's; block with text, not a checkable blocker"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0551279d5c3f7e44
---

## j158: relay made unreachable for one scratch login by an nft uid rule; root is the owner's; block with text, not a checkable blocker

The relay for project agent-fabric is http://127.0.0.1:8765 (projects/agent-fabric/integration/gzcoord/config.json). A "relay stopped for one login" cut for a live check is an nft output rule by uid (`meta skuid <uid> tcp dport 8765 counter reject with tcp reset`, own table, undone by deleting the table); nft needs root, which an agent lacks, so the owner runs it, with a before/after curl as the control and the rule's counter as proof the run reached for the relay. Which uid each provisioning step runs under was not verified: the counter tells.

**Why:** W14's acceptance is "provisioned on a host with the relay stopped"; stopping the relay would cut every account.
**How to apply:** `fabric-jobs block <id> "owner: <decision>"` takes text for an owner's wait (a `--on` flag or an unparsable blocker is refused); `switch` after it still wants a memory change; a paused job is resumed by switch, a blocked one is not.

*Anchors: `projects/agent-fabric/integration/gzcoord/config.json::relay_url`*

*Observed 2026-11-17 (python-dev)*
