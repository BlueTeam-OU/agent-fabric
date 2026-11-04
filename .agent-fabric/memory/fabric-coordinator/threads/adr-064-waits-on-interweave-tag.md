---
role: "fabric-coordinator"
class: threads
topic: "adr-064-waits-on-interweave-tag"
description: "before starting the ADR-064 InterWeave carrier build, check for a tagged InterWeave release; none existed on 2026-10-24"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0865490ea157ca4b
---

## before starting the ADR-064 InterWeave carrier build, check for a tagged InterWeave release; none existed on 2026-10-24

ADR-064's build (roster schema, provisioning, then carrier and adapter REQUESTs) is gated by §5 rule 4 and §6: the programs install only from a tagged InterWeave release archive, and nothing builds before one exists. Tagging is the owner's.

On 2026-10-24 BlueTeam-OU/InterWeave had no tag and no release (`gh api repos/BlueTeam-OU/InterWeave/tags`, `gh release list -R BlueTeam-OU/InterWeave` both empty). This host has no InterWeave working copy under ~/projects, so check the remote, not a clone. The coordinator job (j362) was blocked "owner: tag an InterWeave release" rather than started on the schema early.

**Why:** a schema built before the pinned release would pin against what `transportctl identity show` prints in an untagged tree.
**How to apply:** when the job resurfaces, re-run the two checks; with a tag, pin its version first (§7 build order), then the roster schema. See [[gzcoord-not-on-interweave]].

*References: gzcoord-not-on-interweave*

*Observed 2026-10-24 (fabric-coordinator)*
