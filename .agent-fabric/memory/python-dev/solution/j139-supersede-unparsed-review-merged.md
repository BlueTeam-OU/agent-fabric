---
role: "python-dev"
class: solution
topic: "j139-supersede-unparsed-review-merged"
description: "j139 PR 565 merged — gate 4c Supersedes: <review-id> line lifts an unparsed review; what it lifts and review/arm traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 44dee6ca9dff607d
---

## j139 PR 565 merged — gate 4c Supersedes: <review-id> line lifts an unparsed review; what it lifts and review/arm traps

#565 merged 2026-11-12 (head 463be887). `arm_findings._superseded` returns ids named by `^Supersedes: <digits>$` lines in LATER (GitHub id order) reviews of a trusted login whose first line is the v2 marker; `read()` skips an unparsed (no lines / malformed) review in that set, still advancing its chain. Parsed reviews, no-body and no-id reviews are never lifted. The arm refusal lists `got.supersedable` ids.

- Owed: F5 (P3) — a test that the refusal text without supersedable ids says "ask again" and not Supersedes (deferred at arm; j140 carries it).
- Mutation traps: a test naming an absent id HIGHER than the superseder's passes for the wrong reason (the later check refuses it); use a lower absent id plus a two-unparsed case. A non-v2 trusted superseder must not lift.
- Security-boundary arm (arm.py, arm_findings.py under 8 work): coordinator DECISION with `AUTHORIZES: repo#n@head`, then `fabric-pr arm --authorization <msg-id> --basis ... --defer <head8>:F<n> "<why>"`.
- Fedora platform-smoke flaked once on test_trial_merge grace/KILL timing; `gh run rerun <run> --failed` passed.
- post-review needs the bare command (no cd, no 2>&1); a review posted after a fix push records on the older head, then re-review via `fabric-review save` + `next`.

**Why:** next session on gate 4c or a similar arm rule.
**How to apply:** touching arm_findings or carrying a boundary PR.

*Anchors: `tools/fabric/github/arm_findings.py::_superseded`, `tools/fabric/github/arm.py::check_open_findings`*

*Observed 2026-11-12 (python-dev)*
