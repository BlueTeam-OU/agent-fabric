---
role: "python-dev"
class: threads
topic: "j150-review-server-plan"
description: "j150 (ADR-065 A+B review MCP server) delivered 2aea1b0c, folded in #358; round 1 (C1 blame ignoreRevsFile, C2 git-dir allowlist, R3 quotePath) is j151"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 257539aae1fdb1fd
---

## j150 (ADR-065 A+B review MCP server) delivered 2aea1b0c, folded in #358; round 1 (C1 blame ignoreRevsFile, C2 git-dir allowlist, R3 quotePath) is j151

Delivered: `develop-qzapp/python-dev-01/for/user/j333-review-server` 2aea1b0c, folded unrebased into #358 (merge 3eb1ea7d). Code: tools/fabric/review_mcp/{scope,runner,gittools,sandbox,server}.py,
bin/fabric-review-mcp, tests/test_review_mcp.py (plain script, 48 mutations in a copy+restore script, all killed). Commit from the feat/ worktree
`~/projects/agent-fabric-j150-adr-065-a-b-the-review` (the commit hook refuses the other); push HEAD:refs/heads/...for/user/j333-review-server with the gh credential helper inline.

**Why:** j151 = REQUEST 01a16ac4 (#358 round 1): C1 blame.ignoreRevsFile symlink read (survey every file-valued git config key; PR symlink marker test),
C2 bind an allowlist of the git dir not mask config (config.worktree both places, hooks, logs unreadable; git log still works), R3 core.quotePath=false
(test against review_coverage.diff_paths). Commits carry `Answers: #358 round 1 C1`; suite green on head merged onto #358 head b39d96fe.

**How to apply (traps met):**
- Sleepers a killed mutation run leaves make a later run's process scan fail for the wrong reason: tag each sleep with the run's pid; kill strays by exact pid.
- bwrap: mount tmpfs /tmp and home BEFORE the binds (a worktree under /tmp is hidden otherwise); /dev/null cannot be ro-bound as a file (nodev): use --ro-bind-data with a memfd and pass_fds.
- A proof cache keyed without the bwrap binary lets a fake bwrap ride a real proof; fake bwrap scripts (exit 0; exec "$@") are the counterfactuals.
- A write probe left in the tree when the sandbox wrote it: unlink in finally.
- Pager/fsmonitor/hooksPath are not observable by any verb used: argv pins only; textconv/ext-diff have layered guards, so one mutation must drop all layers.
- Full suite on a branch citing an ADR not yet on main reds two lint cases until the record is folded.

*Observed 2026-10-23 (python-dev)*
