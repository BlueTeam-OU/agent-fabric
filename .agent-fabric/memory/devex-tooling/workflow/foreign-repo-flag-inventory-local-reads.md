---
role: "devex-tooling"
class: workflow
topic: "foreign-repo-flag-inventory-local-reads"
description: "giving a tool a --repo (act on another repository than the cwd's): list every place it reads local state — the cwd clone's git, its config files, env a child command drops — and redirect or refuse each; one forgotten read answers for the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 17a5ea37f87818a9
---

## giving a tool a --repo (act on another repository than the cwd's): list every place it reads local state — the cwd clone's git, its config files, env a child command drops — and redirect or refuse each; one forgotten read answers for the wrong repository

`fabric-pr --repo` (j146, agent-fabric #300/#304, 2026-10-18..19) set GH_REPO and the project
variable in the dispatcher. Three later rounds each found another read that still answered for the
cwd:

1. **A child drops the variable.** arm calls `fabric-pr gate`/`review-status` as subprocesses, and
   the child dispatcher pops AGENT_FABRIC_PR_PROJECT when it gets no `--repo`. So pr_gate read the
   cwd's pr-tools.json for the named repository's PR. Fixed with `common.fabric_pr_verb`, which
   passes `--repo` on.
2. **The count reads the cwd clone.** pr_gate fetched and counted commits in the cwd's origin. From
   another repository's checkout it exited 2, and in a fork clone it counted against the wrong
   base. It now counts only when `landed.origin_is(repo)`, and otherwise says whose clone it is.
3. **`--in-flight` and `--overlap` read `refs/remotes/origin/*`** of the cwd clone, so they printed
   its branches as the other repository's. They now refuse. Separately, `origin_is` read
   `git config remote.origin.url`, which skips `url.<base>.insteadOf`. It now accepts the
   configured or the resolved URL.

**How to apply:** before shipping a "target another repository" flag, grep the code it reaches for
every local read: `git -C`/`toplevel()`, `origin`, config files found from the cwd, and env
variables a nested command resets. Mark each one redirected, refused, or provably the same.
Include one test that runs the real nested path (the real gate, not a mock) from a checkout of
another repository, and test each refusal. The design notes and test traps are in
[[j146-pr-repo-flag-design]].

*References: j146-pr-repo-flag-design*

*Anchors: `tools/fabric/github/common.py::def fabric_pr_verb`, `tools/fabric/github/landed.py::def origin_is`*

*Observed 2026-10-22 (devex-tooling)*
