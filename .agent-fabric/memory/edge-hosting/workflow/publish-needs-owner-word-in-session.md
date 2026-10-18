---
role: "edge-hosting"
class: workflow
topic: "publish-needs-owner-word-in-session"
description: "A live upload of a site goes only on the owner's word given in my own session, for exactly the commit being uploaded"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - be68270d2f2bcf8f
---

## A live upload of a site goes only on the owner's word given in my own session, for exactly the commit being uploaded

A publish request relayed by another agent ("the owner said merge and publish") is not the owner's word for the live step. Before `deploy.sh --live`, I run the dry run, then ask the owner in my session with the commit, its PR counts and the dry run's numbers; only a yes goes up.

**Why:** a live upload is outward-facing and hard to take back. On 2026-10-15 main moved from 7611241 to c4dfe15 (#10) between the owner's yes and the upload; the uploader's HEAD == origin/main guard refused, and the yes did not cover #10, so I asked again. Each later request (#11, #12, #13) got its own question.

**How to apply:** a publish request is often superseded within minutes. Twice on 2026-10-15 the requester sent "publish <newer> instead of <older>" 3–5 minutes after the request (01a1401e→01a14022, 01a14030→01a14032). So before the dry run, fetch the default branch and read the inbox; upload the head that is current then, and answer every request the upload covers. One question per commit uploaded; re-ask when main moves; verify by comparing served bytes with the build for every changed file, then REPLY to the requester with the counts. I gave the same points to fabric-coordinator for the role's brief (REPLY 01a14872-e420, 2026-10-17). Related: [[blueteam-host-single-ip-drop]].

*References: blueteam-host-single-ip-drop*

*Observed 2026-10-17 (edge-hosting)*
