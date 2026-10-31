---
role: "fabric-coordinator"
class: workflow
topic: "arming-word-read-settings-override"
description: "Before telling anyone whose word arms a PR, run `fabric-pr arm <n> --dry-run --basis \"<role>'s word\"` — policies/arming.json alone is not the answer"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b2235b739d110a1
---

## Before telling anyone whose word arms a PR, run `fabric-pr arm <n> --dry-run --basis "<role>'s word"` — policies/arming.json alone is not the answer

On 2026-10-25 I told the owner twice that #376 (below the minimum, a security
boundary) needed their "arm 376". It did not: the BlueTeam-OU settings repo's
repos/<repo>.json overrides policies/arming.json per repository (min, the
boundary authority, authority_own_prs), and the dry-run named my role as able to
lift the gate in the owner's place. I had read only policies/arming.json and a
dry-run whose --basis I had typed as "the owner's word", which it echoed back.

**Why:** the fleet default and the per-repository override differ; a dry-run
echoes the basis it is given, so it only answers who may arm when asked with the
basis being tested.
**How to apply:** to learn who may give the word, dry-run with
`--basis "fabric-coordinator's word"` (add --any-owner for another session's PR):
"authorized in the owner's place" means mine; a refusal names who. Holders and
values stay in the records, never here ([[repo-ownership-from-records]],
[[owner-runs-project-arms]]).

*References: owner-runs-project-arms, repo-ownership-from-records*

*Anchors: `policies/arming.json::below_min_authority`, `tools/fabric/github/arm.py::authorized in the owner`*

*Observed 2026-10-25 (fabric-coordinator)*
