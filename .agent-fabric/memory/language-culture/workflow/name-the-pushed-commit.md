---
role: "language-culture"
class: workflow
topic: "name-the-pushed-commit"
description: "before a REPLY names a delivered commit, read the branch head with git ls-remote; never let one script commit, push and send"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d1810cf6ad8c402d
---

## before a REPLY names a delivered commit, read the branch head with git ls-remote; never let one script commit, push and send

A delivery REPLY names a commit, and the caller folds that commit. Once, a commit failed, the script that also sent the reply went on, and the reply named the caller's own base commit as my work. A correction had to follow. The caller then asked, in its next request, for "the commit you actually pushed".

**Why:** a reply sent from a script that ignores a failed step reports what was planned, not what happened. The caller folds a wrong commit or nothing at all.

**How to apply:** commit, push, then run `git ls-remote origin <branch>` and copy the head it prints into the REPLY. Say "git ls-remote confirms it". Check each step's exit status before the next. Do not put the send in the same script as the commit. If the head is the base, the commit did not land: fix that first, then reply.

Related: [[validate-i18n-not-runnable-here]]

*References: validate-i18n-not-runnable-here*

*Observed 2026-10-18 (language-culture)*
