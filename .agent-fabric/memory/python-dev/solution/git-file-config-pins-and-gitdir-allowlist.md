---
role: "python-dev"
class: solution
topic: "git-file-config-pins-and-gitdir-allowlist"
description: "review_mcp (#358 round 1): blame.ignoreRevsFile cannot be pinned by -c; mailmap/orderFile can; bind an allowlist of the git dir; quotePath"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 404a9a211c302524
---

## review_mcp (#358 round 1): blame.ignoreRevsFile cannot be pinned by -c; mailmap/orderFile can; bind an allowlist of the git dir; quotePath

On git 2.56 `-c blame.ignoreRevsFile=` does not clear a repo-config value (list values accumulate, the empty one sorts first); only `blame --no-ignore-revs-file` does. mailmap.file/blob and diff.orderFile are single-valued, so `-c key=` works (orderFile empty errors: use /dev/null). A `.mailmap` symlink in the tree is refused by git itself (ELOOP). Worktrees share the clone's config: set/unset a key once in a test.
The sandbox binds an allowlist of the git dir (objects, refs, HEAD, packed-refs, shallow + the worktree's own HEAD/commondir/gitdir/index); no config there at all. core.quotePath=false keeps paths equal to review_coverage.diff_paths.
**Why:** #358 round 1 C1/C2/R3, commit de043a12 on the j333-review-server for/ branch.
**How to apply:** a new file-valued git key goes in the PINNED survey comment with a symlink-to-marker test; test files with `git hook` text in a heredoc trip the job guard: write scripts with the Write tool.

*Anchors: `tools/fabric/review_mcp/gittools.py::--no-ignore-revs-file`, `tools/fabric/review_mcp/sandbox.py::GIT_COMMON_TREES`*

*Observed 2026-10-23 (python-dev)*
