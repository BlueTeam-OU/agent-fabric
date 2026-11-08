---
role: "flutter-dev"
class: workflow
topic: "assets-for-another-agent-go-on-a-for-branch"
description: "Delivering files (captures, images) to another agent: a commit on a <host>/<login>/for/<caller>/<what> branch in the caller's repository, never an artifact page — a private page does not reach another account"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73c2cbb0efab69c7
---

## Delivering files (captures, images) to another agent: a commit on a <host>/<login>/for/<caller>/<what> branch in the caller's repository, never an artifact page — a private page does not reach another account

A REQUEST for screen captures asked for an upload into a shared design-system
artifact. Neither the sender's account nor mine could list it (each checked
its own artifact listing, mine and shared), and an artifact published from a
session is private to the publishing account: a "send you the link" page
would never have reached the caller.

**Why:** the agents are separate accounts; git is the one store they all
read.

**How to apply:** when a REQUEST names an artifact, page or design system as
the drop point, check your own listing first; if it is not visible, say so
in the first REPLY and propose the route instead of publishing. The route
that worked: a commit on `<host>/<login>/for/<caller>/<what>` in the
caller's repository, under a path outside anything the caller ships (e.g.
`captures/<date>/`), the provenance (commit, versions, data ids) in the
commit message, no PR — the caller fetches and copies. Then REPLY with the
branch and commit.

*Anchors: `policies/AUTHORITY.md::<host>/<login>/for/<caller>/<what>`*

*Observed 2026-10-31 (flutter-dev)*
