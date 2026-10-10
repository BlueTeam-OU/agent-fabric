---
role: "python-dev"
class: domain
topic: "shell-text-secrets-and-git-answers"
description: "porting a shell read or a git check — a token in a child's argv is readable in /proc; rev-parse answers false with exit 0; unknown git state is not clean"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fa2f9c1651c7fbec
---

## porting a shell read or a git check — a token in a child's argv is readable in /proc; rev-parse answers false with exit 0; unknown git state is not clean

Three seams the j31 port (fabric-fresh, fabric-usage) and its reviews found
(branch for/user/port-a, 2026-10-06):

- **A secret in a child's argv is readable by every account on the host**
  in /proc/<pid>/cmdline while the child runs. `curl -H "Authorization:
  Bearer $(jq ...)"` puts it there. Pipe the header to curl instead:
  `jq -r '"Authorization: Bearer " + .token' f | curl -H @- ...`
  (curl 7.55 or later). A port that keeps "the same sh text" carries such a
  leak over, so read the text for argv secrets before freezing it.
- **`git rev-parse --is-inside-work-tree` prints `false` with exit 0** in a
  bare repository or inside .git. Read the answer, not only the exit.
- **A git call that times out or fails inside a working copy is unknown,
  never clean.** The bash read a failed `git status` as clean, and the
  port's own new timeout repeated that. Raise it as an error the caller
  refuses on. Decode with `errors="replace"` when only emptiness matters.
  A non-UTF-8 name is still a change.

**Why:** each was a silent fallback past a reviewer until one fixed the
class. **How to apply:** when porting, list every source of an id that
becomes a path. j39 found three of them (taxonomy, claims role,
shared_with). See [[oracle-blind-spots-in-ports]].

*References: oracle-blind-spots-in-ports*

*Observed 2026-10-06 (python-dev)*
