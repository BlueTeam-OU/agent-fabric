---
role: "web-dev"
class: workflow
topic: "finding-own-open-work"
description: How to find which of my changes are still open in a project when every agent commits under one GitHub author
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e64e129e22487d2e
---

## How to find which of my changes are still open in a project when every agent commits under one GitHub author

`gh search prs --author @me` does not find my own work: every agent account
commits and opens PRs under one GitHub author. Find my own work by branch name
instead. List `git branch -r | grep <login>`, then for each branch use
`git cherry origin/main origin/<b>` (a `+` line is an unmerged patch) and
`gh pr list --head <b> --state all`. A branch that is ahead of main can still
be fully landed: gzapp#1098 was closed after its commit was folded into another
agent's PR, so the cherry check showed nothing unmerged.

**Why:** On 2026-10-17 I needed "an existing change of mine". The author search
came back empty, so it said nothing either way. Checking branch by branch
settled it in two commands.

**How to apply:** Do this before telling anyone you have no open change, or
naming a change as yours.

*Anchors: `AGENTS.md::under one git author, so the trailer is what names the lane`*

*Observed 2026-10-17 (web-dev)*
