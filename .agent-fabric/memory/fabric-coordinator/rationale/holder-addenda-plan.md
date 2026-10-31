---
role: "fabric-coordinator"
class: rationale
topic: "holder-addenda-plan"
description: "Holder addenda (ADR-060 to write): per-agent charter/brief addenda in fabric-agent-<id>/settings/roles/<role>/; owner decisions of 2026-10-17"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b60a9ef22dc33153
---

## Holder addenda (ADR-060 to write): per-agent charter/brief addenda in fabric-agent-<id>/settings/roles/<role>/; owner decisions of 2026-10-17

The owner approved (2026-10-17) the plan at ~/.claude/plans/smooth-dreaming-tide.md: holder-specific `charter-addendum.md` / `brief-addendum.md` (+ `holder.json`) under `settings/roles/<role>/` of the agent's private store, rendered after the shared charter and brief, only for the bound role, keyed by agent id. First users: legal-expert-ee-eu/-ch/-ge, then language-culture (locale chosen by holder.json, not the login suffix; locale.json's deployment fields move there; charter L73-82 to the -en addendum).

Owner decisions: (1) only the parent writes addenda; at launch the last commit on the path must be parent-signed; (2) legal-expert is `holders_specialize: required` once the shared text is jurisdiction-free: no valid addenda = launch refused; (3) Georgian addenda carry an English gloss (`<name>.gloss.en.md`, `glosses_digest`), never rendered.

**Why:** two holders of one role need different permanent specialization; repeated assignment prompts were standing in for it, and the login-suffix locale key breaks on a rename.
**State (2026-10-17):** ADR-060 accepted by the owner and merged (#289); mechanism branch develop-qzapp/user/feat/holder-addenda-mechanism folds python-dev-02 (validator), -01 (read path), -04 (write path); the lint rule over children mirrors was dropped (install and render already validate). Locale amendments (ADR-018/027/057) wait for stage 3 (python-dev-03, j54).
**State (2026-10-18):** stages 1-5 merged (#289-#295); addenda re-issued; holder.json installed for legal-expert-ge (f82a566), language-culture-ge (1ff0d9d), -ru (f9efd9d), the only holders whose locale is not English. Stage 6 live checks requested of those three; the suffix fallback is removed only after their REPLYs and the owner's go-ahead.
**How to apply:** sequence: briefs PR first, then ADR-060 + amendments (ADR-002, 027, 038, 042), then the inert mechanism (python-dev, contract), holder.json, addenda installs, then one cleanup PR. Every stage leaves every agent launchable. See [[owner-assignment-text-is-role-guidance]].

*References: owner-assignment-text-is-role-guidance*

*Observed 2026-10-18 (fabric-coordinator)*
