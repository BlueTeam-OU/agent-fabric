---
role: "fabric-coordinator"
class: rationale
topic: "agent-fabric-min-8-bundle-jobs"
description: "owner 2026-11-14: agent-fabric PRs arm at 8 work commits like gzapp; below 8 only coordinator's or owner's word; agents bundle jobs to reach 8 (replaces j807 same-topic rule)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91186deed08ac062
---

## owner 2026-11-14: agent-fabric PRs arm at 8 work commits like gzapp; below 8 only coordinator's or owner's word; agents bundle jobs to reach 8 (replaces j807 same-topic rule)

The owner said this in the coordinator's session on 2026-11-14: "agent-fabric CI have become so long in execution-time that PR should move to 8 minimum commits like gzapp ... and agents must be incoraged to put together even jobs to reach 8".

Answers to my follow-up question, the same day:
- **Who may arm below 8:** the coordinator and the owner. The coordinator's word stays available, rarely and stated in the basis.
- **When it applies:** to new PRs only. #609 kept my AUTHORIZES and #610 (3 work, 1 fix) was armed on my word.

**Before:** agent-fabric-settings `repos/agent-fabric.json` had `commits.min: 1`, so a PR armed at one work commit. gzapp uses the fleet default of 8.

**Why:** each PR runs a long CI. Fewer, bundled PRs cost less CI time than many one-commit PRs.

**How to apply:**
- Bundle unrelated jobs onto the open PR until it has 8 work commits. This replaces the owner's 2026-11-12 rule (j807) that only same-topic work rides the open PR.
- Do not give a below-minimum word as routine. Give it only for urgent work, such as the h2 cutover path or a broken main.
- The change itself is job j885: the settings repo, then the skill, team text, ADR-019 and auto-mode text.

Related: [[sixteen-work-commits-not-a-limit]], [[next-work-rides-the-open-pr]], [[h2-agents-live-first]].

*References: h2-agents-live-first, next-work-rides-the-open-pr, sixteen-work-commits-not-a-limit*

*Observed 2026-11-14 (fabric-coordinator)*
