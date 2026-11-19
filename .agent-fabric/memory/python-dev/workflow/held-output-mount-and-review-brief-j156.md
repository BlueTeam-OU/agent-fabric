---
role: "python-dev"
class: workflow
topic: "held-output-mount-and-review-brief-j156"
description: "j156 #628 arming: a second walk (held_output) missed the mount list; re-review request traps; push needs the gh credential helper"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 949884b785a09a4a
---

## j156 #628 arming: a second walk (held_output) missed the mount list; re-review request traps; push needs the gh credential helper

#628 (j152/j153/j154) merged 2026-11-16 on the owner's word, 6 work commits under the minimum of 8.
- When a walk gains a pruning rule (same_device -> mounts), every caller of the walk must collect what it prunes: held_output was the third caller and said "" (clean) for a mount. Grep the callers of the changed function, not only the one in the finding.
- `fabric-review next REQ --pr N` refuses a request whose range ends in `HEAD` ("previous range's head 'HEAD' is not a commit id"): write the reviewed head sha into `range:` first. Round 1 of a PR needs `fabric-review save N 1 < report` before `next`.
- `fabric-pr arm` with checks pending is BLOCKED; poll `gh pr checks`, then arm with `--basis "the owner's word: arm N"`.
- `fabric-jobs done jN pr:628` is refused ("names no repository"): write `BlueTeam-OU/agent-fabric#628`.
- Push still needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.
**Why:** each cost a round trip. **How to apply:** next re-review/arm of a PR.

*Observed 2026-11-16 (python-dev)*
