---
role: "edge-hosting"
class: workflow
topic: "publish-needs-owner-word-in-session"
description: "A live upload of a site goes only on the owner's word given in my own session, for exactly the commit being uploaded"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1bec759817c33712
  - be68270d2f2bcf8f
  - cf773e0de2abded9
---

## A live upload of a site goes only on the owner's word given in my own session, for exactly the commit being uploaded

A publish request relayed by another agent ("the owner said merge and publish") is not the owner's word for the live step. Before `deploy.sh --live`, I run the dry run, then ask the owner in my session with the commit, its PR counts and the dry run's numbers; only a yes goes up.

**Why:** a live upload is outward-facing and hard to take back. On 2026-10-15 main moved from 7611241 to c4dfe15 (#10) between the owner's yes and the upload; the uploader's HEAD == origin/main guard refused, and the yes did not cover #10, so I asked again. Each later request (#11, #12, #13) got its own question.

**How to apply:** a publish request is often superseded within minutes. Twice on 2026-10-15 the requester sent "publish <newer> instead of <older>" 3–5 minutes after the request (01a1401e→01a14022, 01a14030→01a14032). So before the dry run, fetch the default branch and read the inbox; upload the head that is current then, and answer every request the upload covers. One question per commit uploaded; re-ask when main moves; verify by comparing served bytes with the build for every changed file, then REPLY to the requester with the counts. I gave the same points to fabric-coordinator for the role's brief (REPLY 01a14872-e420, 2026-10-17). Related: [[solution-carried-2026-10-18]].

The same holds for any live change, not only an upload. On 2026-10-19 a relayed "owner said pause the status-page workers" (01a154a6) was retracted 14 s later as misaddressed (01a154a6-c03b). The coordinator reissued it 2.5 min later (01a154a8). So read the inbox once more before the live step. If a request was retracted, say plainly that nothing changed, and close its job with `fabric-jobs drop`.

Same on 2026-10-30 for blueteam.ee 19858f4 and 61e5168. Both requests were relayed as "the owner asked" (01a18ce8-3952, 01a18da1). I answered first that the live step waits for the owner's word in my session (01a18ce8-e950). Then for each commit I asked the owner in my session, re-checked origin/main just before `--live`, and replied with the counts and the sha256 comparison (01a18cec, 01a18da3).

*References: solution-carried-2026-10-18*

*Observed 2026-10-17 (edge-hosting)*
