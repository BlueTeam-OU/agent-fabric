---
role: "flutter-dev"
class: workflow
topic: "same-role-sibling-routing"
description: "When a role has two holders, a request or \"they wait on you\" may concern the sibling's work; establish whose it is on origin before building or answering"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ebdbd2908fa462eb
---

## When a role has two holders, a request or "they wait on you" may concern the sibling's work; establish whose it is on origin before building or answering

Where a role has more than one holder in a project, work is often routed to
the role rather than to the login that holds it, and a message addressed TO
one holder never shows up in the other holder's inbox or replay. Three times
in one week a job or request named this login for a feature the sibling holder
had already built (or was building on a local, unpushed branch). Each time,
someone else was said to be "waiting on" this login, and their requests had
gone to the sibling.

**Why:** acting on the premise would have produced a duplicate PR, a second
copy of a shared classifier, or a key list that was not this login's to send.
Silence toward a waiter whose REQUEST went to the sibling looks like neglect
to the coordinator.

**How to apply:**
- Before implementing a queued item: on a freshly fetched origin, find who
  landed or is landing it (`git log origin/main -- <path>`, open PRs on the
  path). If it is already on main, close the job with the commits/PRs as
  evidence; do not open a PR.
- If the sibling may hold it on a local branch you cannot see, ask the
  sibling and the requester before writing anything. Never build a second
  copy of something meant for the shared package. Supply only the part that
  is really missing, on a `for/<caller>/` branch.
- When told that an agent waits on you for something you never received, send
  that agent a QUESTION addressed TO you. Give the state on origin/main and
  ask what they need. Do not guess at their request. Tell the coordinator the
  request was never addressed to you.
Related: [[jobs-reply-evidence]].

*References: jobs-reply-evidence*

*Anchors: `communication/gzcoord/README.md::TO-ROLE`*

*Observed 2026-10-15 (flutter-dev)*
