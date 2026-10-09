---
role: rust-ui-dev
class: recall
description: "Where rust-ui-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources."
tier: 2
distilled_at: 2026-10-01
---

# Deep recall

What this role knows lives in three places, and each answers a different
question.

- **The charter** (`identities/roles/rust-ui-dev/charter.md`, here) — what the
  function is. The project's remit for it
  (`<working copy>/.agent-fabric/roles/rust-ui-dev.md`) — what the function
  covers in that repository.
- **The distilled slices** — `memory/domains/rust-ui-dev/` here for the field,
  `<working copy>/.agent-fabric/memory/rust-ui-dev/` in the project for the
  system. Each is a claim with provenance; the project's `INDEX.md` for
  this role lists all of them with the cue that says when to open one.
  They answer "what is true".
- **This agent's own memory** (`~/.claude/projects/…/memory/`, one fact per
  file) — the raw layer the slices are distilled from, and where a new
  durable fact goes first (with a `roles_class`, so the next drain takes
  it). It answers "what happened", for this agent.

To trace a claim to its sources, use the citation graph rather than
memory — it resolves against git and the forge, and it outlives any
session:

    fabric-query adr <ADR-id>        # who learned from it, where it landed
    fabric-query obs <content-hash>  # the slice(s) a derived_from hash feeds
    fabric-query roles               # what roles exist, per project, and how big

A slice that disagrees with the tree is wrong, not the tree; write the
correction at its source memory, or as a memory of the same class
carrying `merge_target` with the stale section's heading; the next drain
puts it in place.
