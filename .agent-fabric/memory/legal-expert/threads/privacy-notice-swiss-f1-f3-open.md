---
role: "legal-expert"
class: threads
topic: "privacy-notice-swiss-f1-f3-open"
description: "blueteam.ee privacy notice: section 10's Swiss OpenAI sentence dropped on the owner's F3 (8918d30d); what stays open"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 17451f1ab93eaa94
---

## blueteam.ee privacy notice: section 10's Swiss OpenAI sentence dropped on the owner's F3 (8918d30d); what stays open

The privacy-notice draft (docs/legal/2026-10-15-privacy-notice-blueteam-ee-draft.md) took the owner's F3 on 2026-11-10 in commit 8918d30d on develop-qzapp/legal-expert-ee-eu/for/user/j20-privacy-notice-owner-facts: no personal data of persons in Switzerland reach OpenAI, so section 10 says nothing of a Swiss safeguard for OpenAI's US copy. F1 (Swiss-US DPF certification) does not hold; F2 (Swiss adaptations) is not in OpenAI's public DPA (its Schedule 1 s.8 completes the SCCs for UK data only, read 2026-11-10). legal-expert-ch's opinion 0624d246 is the Swiss reading.

**Condition:** F3 holds only while no Swiss persons' data go into OpenAI, including client data a Swiss client agreed to in writing under section 5. If that changes, section 10 changes first, with ch's F1/F2 sentence (their section 6).

**Closed 2026-11-11** by the owner: 1984 logs 90 days; OpenAI DPA effective 2026-01-01 accepted ([[privacy-notice-j24-owner-closes]]). Fold is fabric-coordinator's j755 (REQUEST 01a1c747-6571-7601-8b2d-ab3c6a2d6fa3); brand-comms-01 told for its j55 (INFO 01a1c747-67df-77b2-a58b-949c913473b8).

**How to apply:** the commit hook refuses a feat/ job branch and the job guard refuses committing in another job's worktree; commit on a new local for/user branch in the job's own copy and push HEAD to the remote for/user ref ([[job-branch-feat-refused-use-for-user]]).

**Merged 2026-11-11** in #551. The review's Risks note asked whether to reopen [FACT] marks on 1984 logs, the OpenAI DPA version and Smart Accounts hosting; I judged no (owner-supplied facts, recorded), and advised the owner to read 1984's log setting before brand-comms publishes (REPLY 01a1ca0d-70c5-7fb8-9993-23e6fdfe9a3b).

*References: job-branch-feat-refused-use-for-user, privacy-notice-j24-owner-closes*

*Observed 2026-11-11 (legal-expert)*
