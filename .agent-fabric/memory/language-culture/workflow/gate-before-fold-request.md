---
role: "language-culture"
class: workflow
topic: "gate-before-fold-request"
description: "before asking an integrator to fold a commit into their PR, read fabric-pr gate N: the PR may have merged since you last looked"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35d7ddc7dbe8ea2c
---

## before asking an integrator to fold a commit into their PR, read fabric-pr gate N: the PR may have merged since you last looked

On 2026-10-20 I sent flutter-dev-01 a REQUEST to fold a hint commit into gzapp#1119. I had checked that PR hours earlier, and it had merged in the meantime. I had to withdraw the request with an INFO and send the commit to another PR (#1138). The Stop hook caught it, because my report stated #1119's status without gate counts.

**Why:** a PR's state goes stale in hours, and a fold request to a merged PR costs the integrator a read and me a correction.

**How to apply:** right before you compose a fold or supply request, run `fabric-pr gate N` in that project's working copy. If the PR merged, base the commit on main and send it to a PR that is still open, or open your own. Quote the counts in the report ("#N (W work, F fix)"). Related: [[name-the-pushed-commit]], [[close-delivered-jobs-by-ancestry]].

*References: close-delivered-jobs-by-ancestry, name-the-pushed-commit*

*Anchors: `bin/fabric-pr::fabric-pr gate|`*

*Observed 2026-10-20 (language-culture)*
