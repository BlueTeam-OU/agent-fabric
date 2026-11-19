---
role: "fabric-coordinator"
class: workflow
topic: "answered-request-close-the-job"
description: "a REQUEST answered by a \"no + routes\" REPLY leaves its job active; close it the same turn"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e5c7bfda941df3f
  - e0722be8a0d09591
---

## a REQUEST answered by a "no + routes" REPLY leaves its job active; close it the same turn

j426 (REQUEST 01a17c3c, a shell into interweave-deploy) was answered on 2026-10-27 with REPLY 01a17c3d, a no with the reason and two other routes, and the requester took one of them (REPLY 01a17c40). The job stayed active anyway and opened a fresh session on 2026-10-30 that had nothing left to do.

**Why:** the acceptance allowed "or a no, with the reason", so that REPLY was the whole delivery. A reply is not a commit, though, so nothing moved the job.

**How to apply:** when a REPLY is the deliverable, run `fabric-jobs done <id> --no-artifact "<reply ids, what was decided>"` in the same turn. Before starting any job that came from a request, read its thread (`fabric-history --thread <id> --full`), because it may already have been answered.

**Second instance, 2026-11-10 (j743).** An AUTHORIZES REPLY (01a1c4a3) to python-dev's REQUEST for #547 was the whole delivery. The job was left `blocked on pr:BlueTeam-OU/agent-fabric#547` instead of being closed. When the PR merged, the blocker cleared and the job came back as active in a fresh session with nothing to do. An AUTHORIZES REPLY is delivered once it is sent: close the job then (`fabric-jobs done <id> --no-artifact "AUTHORIZES <reply id> for #N@sha"`). Never block it on the PR, which belongs to the requester.

*Anchors: `tools/fabric/jobs.py::--no-artifact`*

*Observed 2026-11-10 (fabric-coordinator)*
