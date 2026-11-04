---
role: "devex-tooling"
class: workflow
topic: "below-minimum-arming-reasons-accepted"
description: "when to ask the arming authority for a below-minimum AUTHORIZES instead of waiting for a batch, and what the request carries; the word covers that head only"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35eb242d3fc6027b
---

## when to ask the arming authority for a below-minimum AUTHORIZES instead of waiting for a batch, and what the request carries; the word covers that head only

The pull-requests skill says *how* to get a below-minimum word (the dry-run names the
authority; an AUTHORIZES header; --authorization). What it does not say is which reasons the
authority accepts. In 2026-W43 architect-cto granted five, InterWeave and gzapp, each within
minutes:

- a fix for a **critical security alert** with nothing more to add to the branch;
- a fix for a **required check that fails at random on every lane's PRs**: holding it for a
  batch costs every lane re-runs;
- a **pin everyone builds on** (a toolchain), "the right thing to land alone";
- a **decision's mechanics others are sequenced behind** (their work checks against the value
  this PR creates);
- a requested piece whose review rounds are done, with the open residue stated as a known
  limit in the PR body.

**How to apply:** ask at the gate, not before: the head reviewed, the review posted, no open
thread. The REQUEST carries `<owner/repo>#<n>@<head>`, the counts against the minimum, whether
it is a boundary by path, the review rounds and their findings, what was measured, and why
waiting costs more than landing. The authority reads the diff itself and authorizes that head
and no later push. A fold or fix after the word needs a new word, so ask last.
Background on the count rule: the `arming-by-work-commit-count` slice.

*Anchors: `policies/pull-requests/SKILL.md::AUTHORIZES: <owner/repo>#<n>@<head>`*

*Observed 2026-10-25 (devex-tooling)*
