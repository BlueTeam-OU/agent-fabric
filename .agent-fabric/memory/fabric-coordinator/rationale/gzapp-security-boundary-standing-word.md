---
role: "fabric-coordinator"
class: rationale
topic: "gzapp-security-boundary-standing-word"
description: "Owner 2026-10-05 — the standing \"over 8 commits arm without my authorization\" covers gzapp security-boundary PRs too (8–16 work commits)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 49959da55c68b559
---

## Owner 2026-10-05 — the standing "over 8 commits arm without my authorization" covers gzapp security-boundary PRs too (8–16 work commits)

The owner ruled on 2026-10-05, answering a question raised by gzapp#1037's
review: their standing word of 2026-09-27 ("over 8 commits a pr can be armed
without my authorization, just complete the job") covers **security-boundary**
PRs in gzapp too, at 8–16 work commits. The review gate, 19b's security
dispatch and resolved threads still apply. Over 16 needs no word either (owner, same day: "over 16
commit don't require my authorization"); only under 8 is the owner asked.

**Why:** backend-dev-02 and backend-dev-01 had drained contradictory memories
(one arming such PRs on the standing word, one requiring the owner's word per
change, matching gzapp's CLAUDE.md lines ~808 and ~945); both slices were held
back from the 2026-10-05 drain pending this ruling.

**How to apply:** architect-cto-01 was asked (GZCoord 01a10d7d-fb9e…) to amend
gzapp's CLAUDE.md; backend-dev-01 to retire its correction, backend-dev-02's
restatement stands. Check at the next drain that the arming slice lands and
the correction does not. Related: [[arm-in-band-on-my-own]].

*References: arm-in-band-on-my-own*

*Observed 2026-10-05 (fabric-coordinator)*
