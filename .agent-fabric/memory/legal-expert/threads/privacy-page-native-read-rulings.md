---
role: "legal-expert"
class: threads
topic: "privacy-page-native-read-rulings"
description: "j25: rulings on the blueteam.ee privacy page native read, applied in 71d0b5ff; Telegram kept; header fixed in 25a823fb"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 97738b6e36c1df4b
---

## j25: rulings on the blueteam.ee privacy page native read, applied in 71d0b5ff; Telegram kept; header fixed in 25a823fb

REPLY 01a1caeb-36a3-7db5-bb4f-4e83c4d3fedc to brand-comms-01 (REQUEST 01a1cae9), page src/pages/privacy.astro at 5c49357: yes to "(business subscription)", drop "only" in section 4, "OpenAI's tools" in section 5, data-protection contact "at info@blueteam.ee", section 6 reorder with "these clauses" and "says about", "make and perform", "Work in a client's systems.", "before you withdrew it". Own wording for invoices: "7 years from the end of the financial year in which we recorded the invoice" (RPS § 12(1) counts from the year the transaction was booked; RT I, 10.07.2025, 3, read 2026-11-11). Telegram in section 7: drop it if the owner says BlueTeam has no Telegram account.

**Applied 2026-11-11:** commit 71d0b5ff on develop-qzapp/legal-expert-ee-eu/for/user/j24-privacy-notice-header-owner-closed (pushed, on top of 60a124a6); fabric-coordinator (login `user`) told the fold now has two commits (REPLY 01a1caee). j25 delivered by reply:01a1caeb. ~/handoff/j25-draft-rulings.patch can go. Owner, 2026-11-11 (to me directly): BlueTeam has a Telegram account, so section 7 keeps it. brand-comms-01 told the legal text is final and to publish (REPLY 01a1cb81). Fold: coordinator folded 60a124a6+71d0b5ff into agent-fabric#557 (REPLY 01a1cb5b). Draft header line on Telegram still says 'waits on the owner': fixed in j26: commit 25a823fb on the same for/user branch (final but for the date), coordinator told by INFO 01a1cb84 to fold it into #557. Committing it needed a for/user/ local branch, since the hook refuses a feat/ job branch ([[job-branch-feat-refused-use-for-user]]), and a git merge in another job's worktree is refused (ADR-037 rule 3). Builds on [[privacy-notice-j24-owner-closes]].

*References: job-branch-feat-refused-use-for-user, privacy-notice-j24-owner-closes*

*Observed 2026-11-11 (legal-expert)*
