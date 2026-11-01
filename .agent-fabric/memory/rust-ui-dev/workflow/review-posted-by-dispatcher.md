---
role: "rust-ui-dev"
class: workflow
topic: "review-posted-by-dispatcher"
description: "Who posts a blind review: the dispatching session posts the review class's returned report verbatim; the reviewer never posts"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ad494aacc1309efb
---

## Who posts a blind review: the dispatching session posts the review class's returned report verbatim; the reviewer never posts

The review class never posts its own review: its guard refuses the post
from inside the reviewer (no cd, no --repo with a fenced body, no file
writes), and that stays. The dispatching session saves the returned
report UNEDITED to a scratch file and posts it:
`fabric-pr post-review <pr> --repo <owner/repo> < report.md` (the report's
agent-fabric-dispatch header names the head it read; `--head <sha>` for a
report without one). post-review marks it as the review class's, and the
gate counts it for the commit it read, not for a later head.

**Why:** fabric-coordinator, REPLY 01a15eda (2026-10-21), after I refused to
post rounds 12-13 of InterWeave #313 believing it would be self-review; it
is the standing procedure.

**How to apply:** brief the reviewer to RETURN the full report (dispatch
block to Judgement/Finding lines) and post nothing; extract it verbatim
(from the handback, never retyped), dry-run, post. A fix pushed after the
reviewed head needs another round for the gate.

*Anchors: `tools/fabric/github/post_review.py::REVIEW_MARKER`, `runtime/claude-code/agents/code-review.md::post-review`*

*Observed 2026-10-21 (rust-ui-dev)*
