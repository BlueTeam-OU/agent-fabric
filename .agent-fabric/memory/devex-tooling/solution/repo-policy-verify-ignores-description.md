---
role: "devex-tooling"
class: solution
topic: "repo-policy-verify-ignores-description"
description: "fabric-repo-policy verify says \"matches\" while a settings record's description still says \"no ruleset\" — prose is never compared; re-read it after an apply"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d4af6b0ee60599c5
---

## fabric-repo-policy verify says "matches" while a settings record's description still says "no ruleset" — prose is never compared; re-read it after an apply

`fabric-repo-policy verify BlueTeam-OU/agent-fabric-gateway` printed "GitHub matches the arming policy" (2026-10-24) while
repos/agent-fabric-gateway.json's description still said "Live today: no ruleset ... merge, squash and rebase are all allowed".
The ruleset 24884009 (pull_request merge-only + required check rust) and squash/rebase off were applied under REQUEST 01a12b39
(2026-10-11) without the description being rewritten. verify compares values only; signatures/protect false were right all along.
**How to apply:** after applying settings to GitHub, rewrite each touched record's "Live today" sentence in the same change,
dated, from `gh api repos/<r>/rules/branches/<default>` and the repo's allow_* flags. Fixed by j217 (REQUEST 01a16fab).
Live read 2026-10-24: rules/branches/main = pull_request (0 approvals, allowed_merge_methods [merge]) + required_status_checks
rust (integration 15368 = github-actions, not strict); no deletion/non_fast_forward/required_signatures rule; allow_merge_commit
true, squash/rebase false, allow_auto_merge true, delete_branch_on_merge false. The record names no method: merge comes from the
fleet default (policies/arming.json) and is now live; no request names a method for the gateway (01a12b39 asked GitHub to match the files).

*Observed 2026-10-24 (devex-tooling)*
