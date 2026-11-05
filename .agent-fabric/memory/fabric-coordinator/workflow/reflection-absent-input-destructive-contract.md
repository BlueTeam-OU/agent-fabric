---
role: "fabric-coordinator"
class: workflow
topic: "reflection-absent-input-destructive-contract"
description: "A contract for a verb that deletes or writes unattended names what an ABSENT input does, apart from an unreadable one: a missing file read through a shared reader comes back as empty or the default, and the verb then acts on it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 509a73e1c91cbdab
---

## A contract for a verb that deletes or writes unattended names what an ABSENT input does, apart from an unreadable one: a missing file read through a shared reader comes back as empty or the default, and the verb then acts on it

Blind review caught the same risk twice in independent tools. A daily, unattended `fabric-jobs tidy` read a missing jobs.json through the shared reader as "no jobs", and so would have removed active jobs' build trees. A settings `apply` read a missing per-repository file as the fleet default and would have PATCHed with it. My own contract for the first had said only "exit 0 unless the job list cannot be read". Mocked tests hid the second, because they never drove the real loader through the 404.

**Why:** absent and empty look the same to a reader written for a fresh account. Only the destructive caller knows that absent means "I am looking in the wrong place".
**How to apply:** in the ACCEPTANCE of any verb that deletes or writes unattended, list three cases: absent (refuse, write nothing, print one line naming the path read), unreadable (the same), and present but empty (valid). The verb prints the path it decided from. The absent-case test drives the real reader and fails on main. Related: [[gate-output-unknown-not-zero]], [[checks-need-a-control]].

*References: checks-need-a-control, gate-output-unknown-not-zero*

*Observed 2026-11-01 (fabric-coordinator)*
