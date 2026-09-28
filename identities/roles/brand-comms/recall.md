---
role: brand-comms
class: recall
description: "Where brand-comms's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources."
tier: 2
distilled_at: 2026-09-15
---

# Deep recall

What this role knows lives in three places, and each answers a different
question.

- **The charter** (`identities/roles/brand-comms/charter.md`, here) — what the
  function is. Each project's remit for it
  (`<working copy>/.agent-fabric/roles/brand-comms.md`) — what the function
  covers in that repository: the decks' asset register and release
  discipline, the website's stage rule and language pages.
- **The distilled slices** — `memory/domains/brand-comms/` here for the field,
  `<working copy>/.agent-fabric/memory/brand-comms/` in each project for
  that surface. Each is a claim with provenance; the project's `INDEX.md` for
  this role lists all of them with the cue that says when to open one.
  They answer "what is true".
- **This agent's own memory** (`~/.claude/projects/…/memory/`, one fact per
  file) — the raw layer the slices are distilled from, and where a new
  durable fact goes first (with a `roles_class`, so the next drain takes
  it). It answers "what happened", for this agent.

To trace a claim to its sources, use the citation graph rather than
memory — it resolves against git and the forge, and it outlives any
session:

```sh
tools/fabric/query.sh commit <sha>      # which slices a commit taught
tools/fabric/query.sh file <needle>     # which slices cite a file
tools/fabric/query.sh obs <hash>        # one observation, forward and back
```

A slice that disagrees with the tree is wrong, not the tree; write the
correction at its source memory, or as a memory of the same class
carrying `merge_target` with the stale section's heading.
