---
role: "language-culture"
class: workflow
topic: "supply-refetch-branch-before-push"
description: "Before pushing a supply onto another agent's branch, fetch that branch; its en-US may have landed and changed the wording"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2de1ac7a3e157eb6
---

## Before pushing a supply onto another agent's branch, fetch that branch; its en-US may have landed and changed the wording

Twice in one evening (gzapp #1119) the branch owner landed their en-US while I translated: once my unpushed commit had to be rebased onto the new head (9300b50fb on a7c4ddabb), once the en-US chose a different wording for the action and I redrafted to it (68d02f0a5) so the act reads the same in both locales. The request describes the meaning; the source for the second pass is the en-US on the branch. Before committing and pushing, fetch the delivery branch; if its head moved, rebase the unpushed commit, re-read the changed en-US and redo the second pass against it; name the head the commit sits on in the REPLY.

*Observed 2026-10-18 (language-culture)*
