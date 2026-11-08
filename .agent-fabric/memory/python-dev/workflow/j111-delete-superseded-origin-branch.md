---
role: "python-dev"
class: workflow
topic: "j111-delete-superseded-origin-branch"
description: deleting an origin branch of a closed PR — prove content landed by subject match, not SHA; gate has no counts for closed PRs
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b178b51ee6597176
---

## deleting an origin branch of a closed PR — prove content landed by subject match, not SHA; gate has no counts for closed PRs

j111 (2026-11-03): owner asked to delete origin branch j37 (fabric-reflect), PR #256 closed unmerged. The fold rebased the commits, so `git log origin/main..branch` still lists them; prove they landed with `git log origin/main --grep=<subject> -F` per commit, then `git push origin --delete`.

`fabric-pr gate <N>` refuses a CLOSED PR ("not at any gate"), so no work/fix counts exist; the pr-counts stop hook still fires if a reply names a closed PR's status — say it has no counts rather than omit the PR.

**Why:** a destructive remote op needs the content check first. **How to apply:** do the subject-match check, delete, `fabric-jobs done --no-artifact`.

*Anchors: `bin/fabric-pr::gate`*

*Observed 2026-11-04 (python-dev)*
