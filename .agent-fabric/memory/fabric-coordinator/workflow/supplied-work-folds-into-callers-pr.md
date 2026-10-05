---
role: "fabric-coordinator"
class: workflow
topic: "supplied-work-folds-into-callers-pr"
description: "Work another role does at my request (a locale re-render, a fix) is folded into MY open PR, never merged as its own PR — owner 2026-10-02 on #81/#82"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 730a8c1e7a858b01
---

## Work another role does at my request (a locale re-render, a fix) is folded into MY open PR, never merged as its own PR — owner 2026-10-02 on #81/#82

Owner, 2026-10-02: "commit like ones of pr 81 82 must be folded in the requesting guy pr". I had asked the ge and ru language-culture holders to re-render `team.md`; each opened its own PR (#81, #82) and I reviewed and was about to merge them separately.

**Why:** the team rule already says a supplier never opens a PR for supplied work; the caller owns the branch, the PR and the arming, and folds the supplier's branch unrebased. A separate PR per supply is the PR-per-topic shape the owner rejected, and it costs a review, a CI run and a merge each.

**How to apply:** every REQUEST I send for supplied work says "deliver a branch `<host>/<login>/for/user/<what>`, open no PR; I fold it into my open PR". If a supplier opens a PR anyway, fold its commits into my branch and close the PR naming where it went. A locale holder's own unrequested work (the carve-out) is still its own PR. Related: [[pr-band-accumulate]], [[correction-requests-name-merge-target]].

*References: correction-requests-name-merge-target, pr-band-accumulate*

*Observed 2026-10-02 (fabric-coordinator)*
