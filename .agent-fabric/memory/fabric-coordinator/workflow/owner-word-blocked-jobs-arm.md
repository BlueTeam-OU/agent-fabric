---
role: "fabric-coordinator"
class: workflow
topic: "owner-word-blocked-jobs-arm"
description: "arming a PR whose branch carries jobs blocked on \"owner: word to arm\" — defer them at arm, then start→done; done refuses a blocked job"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: gzapp.decks
    working_copy: gzapp.decks
derived_from:
  - 9e0d89c4ab63295c
---

## arming a PR whose branch carries jobs blocked on "owner: word to arm" — defer them at arm, then start→done; done refuses a blocked job

A job blocked on free-text "owner: word to arm <pr>" is not cleared by the word arriving: `fabric-pr arm` still refuses (gate on blocked jobs on the branch). Pass `--defer-job j<n> "<why: its blocker is the owner's word, given <date> '<quote>'>"` per job; the reason lands in the arming comment. After the merge, `fabric-jobs done` refuses a blocked/queued job: `fabric-jobs start j<n>` (no reason argument; `why` only with `--despite`) then `done j<n> pr:<repo>#<n> commit:<sha>`. Seen on gzapi-org/gzapp.decks#29, merged dae5ed6d 2026-11-13 (jobs j502, j660).

**Why:** a free-text blocker is not checkable, so nothing clears it automatically; use `--on pr:…` / `request:…` blockers when blocking a job to let it clear on its own.
**How to apply:** when blocking a job on the owner's word, prefer a checkable `--on` blocker; when arming, read the dry-run's REFUSED line for the job ids to defer.

*Anchors: `agent-fabric:tools/fabric/github/arm.py::defer-job`, `agent-fabric:tools/fabric/jobsparts/verbs.py::despite`*

*Observed 2026-11-13 (fabric-coordinator)*
