---
role: "devex-tooling"
class: workflow
topic: "jobs-sweep-cannot-resolve-commit-artifact"
description: "fabric-jobs sweep leaves a delivered job whose only artifact is commit:<sha> — check ancestry yourself and fabric-jobs done"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cd38836d9b1adb6a
---

## fabric-jobs sweep leaves a delivered job whose only artifact is commit:<sha> — check ancestry yourself and fabric-jobs done

`fabric-jobs sweep` closes a delivered job only through an artifact it can resolve to a merged PR;
a job carrying only `commit:<sha>` "stays" even when the commit is on origin/main (j162,
commit:99b33f22, 2026-10-19). Check `git merge-base --is-ancestor <sha> origin/main` after a fetch,
then `fabric-jobs done <id>`. Delivering with a `github-pr:` artifact beside the commit lets sweep
close it itself (j169). See [[job-landed-check-by-commit]].

*References: job-landed-check-by-commit*

*Anchors: `tools/fabric/jobsparts/sweep.py::it can resolve`*

*Observed 2026-10-19 (devex-tooling)*
