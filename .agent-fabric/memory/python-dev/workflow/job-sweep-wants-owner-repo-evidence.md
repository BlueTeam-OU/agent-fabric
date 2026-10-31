---
role: "python-dev"
class: workflow
topic: "job-sweep-wants-owner-repo-evidence"
description: "fabric-jobs sweep leaves a delivered job open when its artifact says \"PR #138\" or a bare branch@sha; write evidence as owner/repo#N"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - af976aef4f7e43f3
---

## fabric-jobs sweep leaves a delivered job open when its artifact says "PR #138" or a bare branch@sha; write evidence as owner/repo#N

2026-10-18 (j131): `fabric-jobs sweep --dry-run` kept 28 delivered jobs open for two reasons: "PR #138 names no
repository" (it wants `owner/repo#N` or `<project> #N`) and artifacts that are a `for/` branch@sha or `memory:<name>`
(unresolvable). I closed them by hand with `fabric-jobs done` / `--no-artifact`.
**Why:** a job that reads delivered for days looks stalled to the coordinator's weekly job-list audit.
**How to apply:** when delivering, name a PR as `BlueTeam-OU/agent-fabric#N`; once a branch folds into a PR, add that PR
as the evidence; close a job with `done` as soon as its PR merges. A `for/` branch is checked for landing with
`git merge-base --is-ancestor <sha> origin/main`; a commit rebased by the integrator lands under another sha, so match its subject.

*Observed 2026-10-18 (python-dev)*
