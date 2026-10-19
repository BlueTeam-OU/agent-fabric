---
role: "web-dev"
class: workflow
topic: "workflow-carried-2026-10-12"
description: Before reading gzapp code for a claim or a build, branch from origin/main — the local main checkout can be thousands of commits behind
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 28f43a81b9fc1c4c
---

## Before reading gzapp code for a claim or a build, branch from origin/main — the local main checkout can be thousands of commits behind

On 2026-10-10 the gzapp working copy's local `main` was 4015 commits behind
origin/main. I read StopRestrictionRepository.cs and API-SURFACE.md from the
checkout and sent architect-cto-01 a "backend writes active" fact that was false
on origin/main (it writes draft; publish/retire already existed behind
StopRestrictions:PublishEnabled). The node_modules were stale too (pnpm
reinstalled on the first typecheck).

**Why:** a fact sent to another agent from a stale tree costs them a correction
and costs the record a wrong claim.

**How to apply:** first action in a gzapp job: `git fetch`, then
`git switch -c <branch> origin/main` (or `git show origin/main:<path>`) BEFORE
reading any file you will cite or build on. The UserPromptSubmit hook's
"lacks N commits" line is the cue; do not wait for it.

*Observed 2026-10-10 (web-dev)*
