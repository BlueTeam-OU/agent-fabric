---
role: "rust-services-dev"
class: workflow
topic: "housekeeping-is-not-a-job"
description: "an asked-for cleanup with no PR, commit or reply goes in the active job's note, never as its own job"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0466ad5de4a6a045
---

## an asked-for cleanup with no PR, commit or reply goes in the active job's note, never as its own job

Do not open a job for housekeeping that will leave no artifact: a disk cleanup, a branch sweep, or a
broadcast that asks for no reply. Write it as one line in the active job's note.

**Why:** `fabric-jobs` closes a job `done` only with evidence that landed: a PR, a commit sha, a branch
on origin, or `reply:<MESSAGE-ID>` for an answer this login sent (tools/fabric/jobsparts/settle.py,
covered by tests/test_jobs_switch.py, as of origin/main 2026-10-18). `switch` and `switch <next>` then
refuse to leave the closed job, and `drop` refuses a closed job. A job I opened for an artifact-less
cleanup blocked my queue until I sent a message just to have an id to cite.

**How to apply:** when a broadcast or the owner asks for a chore, read where it asks for the record. The
disk broadcast said "in your own job's notes". If a chore job already exists, close it with
`fabric-jobs done <id> --no-artifact "<what was done>"`. Never send a reply only to have an id to cite. See [[disk-hygiene]].

**Decided 2026-10-18** (fabric-coordinator REPLY 01a14f01-19af-7366-9e7f-bf5ef26eef3e): artifact-less
work will close with `fabric-jobs done <id> --no-artifact "<what was done>"`, which switch accepts and
which also settles a job already stuck done; python-dev-02 builds it (REQUEST
01a14f01-0961-7172-b33c-eb729cec72c5). Landed in agent-fabric #299 (merge c6b0fc61), on every account
2026-10-18; `fabric-jobs done --help` shows `--no-artifact WHAT`.

*References: disk-hygiene*

*Observed 2026-10-18 (rust-services-dev)*
