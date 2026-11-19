---
role: "python-dev"
class: workflow
topic: "charter-authority-refuses-coordinator-commit-on-my-branch"
description: "a policies/authority.json commit by fabric-coordinator on a contributor's PR still fails CI; and a new test helper file needs the owning role's path first"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8325ef5270a85e2c
---

## a policies/authority.json commit by fabric-coordinator on a contributor's PR still fails CI; and a new test helper file needs the owning role's path first

j135 / #630 (2026-11-16): fabric-coordinator's commit adding a path to `policies/authority.json` on my branch turned guards-and-suites red ("a role's DEFINITION changed on a branch owned by agent 'python-dev-04'"): charter_authority judges the branch owner, not the commit's Fabric-Role. The lint also refuses an authority path not yet in the tree, so a new file's path can only land after the file is on main (their job j911).

**Why:** moving mocks out of a file another role owns (test_arm_cli.py, devex-tooling) into a new file puts them outside that role's paths; the review caught it as a P2.
**How to apply:** before splitting a role-owned test file, check that role's `paths` in authority.json; expect a deferred P2 and a follow-up coordinator PR. Dropping a bad commit from my branch is `git reset --hard <my head>` + `--force-with-lease`, which the auto-mode classifier denies until the owner allows it in words. After a force-push, `main` may conflict: devex-tooling edits mocks inside the old file, so a merge conflict means porting the hunk into the new module. A review is pinned to a head sha: merging main makes a fresh review necessary (use a plain brief on origin/main..head, not `fabric-review next`, whose range would be main's own commits).

*Observed 2026-11-16 (python-dev)*
