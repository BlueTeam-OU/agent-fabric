---
role: shared
class: workflow
topic: "worktree-under-dot-claude"
description: "an isolated subagent's worktree lives in <repo>/.claude/worktrees/; `git add -A` in the main checkout stages it as an embedded repo"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6eb16ceede06eb9a
---

## an isolated subagent's worktree lives in <repo>/.claude/worktrees/; `git add -A` in the main checkout stages it as an embedded repo

A subagent dispatched with isolation "worktree" gets its copy at
<repo>/.claude/worktrees/agent-<id>, inside the main checkout. While it
runs, `git add -A` there stages it as an embedded git repository (it did,
2026-09-30, into ADR-040's acceptance commit; caught before the push).
agent-fabric's .gitignore now ignores .claude/worktrees/ (Wave 1 branch).
**Why:** a stray gitlink in a commit, and fabric-ctl status reads the
checkout as "dirty" meanwhile.
**How to apply:** in any other repository where a worktree agent runs,
stage paths explicitly or check `git status -s` for `.claude/` first.

2026-10-01: the SessionStart hook ran for each worktree subagent with the worktree as cwd and wrote it into the LOGIN's binding (working_copy) — lint then reported INDEX drift for every slice in that worktree, and fabric-status/fabric-jobs read the wrong working copy. Fixed in session-start.py (Wave 3 branch, d31a87e): a subagent start leaves the binding alone. If drift appears again, read binding.json's working_copy first.

*Observed 2026-10-01 (fabric-coordinator)*
