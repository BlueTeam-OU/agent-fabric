---
role: "legal-expert"
class: workflow
topic: "fresh-session-before-new-job-writes"
description: "A job taken on after another ended in this session must start in a fresh session (fabric-jobs switch → fabric-fresh) before any commit or push; drafting first wastes a round"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8844749b35108e36
---

## A job taken on after another ended in this session must start in a fresh session (fabric-jobs switch → fabric-fresh) before any commit or push; drafting first wastes a round

On 2026-11-10 a QUESTION arrived in the session that had worked j18. I added it as j19, started it in place and drafted the opinion. The commit was then refused by the PreToolUse hook. Under agent-fabric ADR-037 rule 3, a session that has worked one job runs no other.

I had to park the draft outside the tree (~/drafts/j19/), pause j19 with a note, run `fabric-jobs switch` and hand over to `fabric-fresh --job j19`.

**Why:** the fresh session must re-read everything, and the asker waits longer.

**How to apply:** when a REQUEST or QUESTION arrives after the session's job is delivered, run `fabric-jobs add --request <id>` and then `fabric-jobs switch` straight away. Do not use `start`. Do the reading and drafting in the fresh session. Related: [[disk-cleanup-at-job-end]].

*References: disk-cleanup-at-job-end*

*Observed 2026-11-10 (legal-expert)*
