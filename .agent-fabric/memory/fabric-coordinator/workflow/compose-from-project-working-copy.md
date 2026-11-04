---
role: "fabric-coordinator"
class: workflow
topic: "compose-from-project-working-copy"
description: "A REQUEST about another project's work is composed from that project's working copy: gzcoord-compose stamps PROJECT from the cwd, and the receiver's job and worktree follow it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66c34e872a951062
---

## A REQUEST about another project's work is composed from that project's working copy: gzcoord-compose stamps PROJECT from the cwd, and the receiver's job and worktree follow it

2026-10-19, Wave 10: I composed five port requests (gzapp, gzapp.decks, herdr, blueteam.ee) from
~/projects/agent-fabric, so each carried `PROJECT: agent-fabric`. The receiver's intake filed the job under
agent-fabric and `fabric-jobs switch` cut its worktree in the agent-fabric clone (web-dev-02's j13, reported by
it). `gzcoord-compose --help`: "FROM, ROLE and PROJECT are this login's", resolved from where it runs; it has no
`--project`.

2026-10-24: devex-tooling's j208 came from my REQUEST about moving an arming policy between two settings repositories, composed in agent-fabric. Its commits landed in clones the job did not name, so job-copy-guard refused them. fabric-jobs has no verb to change a job's working copy, so devex-tooling split the work into one job per repository. brand-comms-01 saw the same with its j28.

**Why:** the header is what a receiver's tooling routes on; a wrong one sends the work to the wrong clone.

**How to apply:** `cd ~/projects/<that project's working copy>` (in a subshell) before `gzcoord-compose` for any
message whose work lives there; check the PROJECT line in the file before `gzcoord-send`. When the commits land in a repository that is no registered project (a settings repository), name each repository in the REQUEST so the assignee files one job per clone. Related:
[[request-needs-a-job]], [[in-reply-to-read-not-typed]].

*References: in-reply-to-read-not-typed, request-needs-a-job*

*Anchors: `tools/fabric/gzcoord/compose.py::are this login's`*

*Observed 2026-10-19 (fabric-coordinator)*
