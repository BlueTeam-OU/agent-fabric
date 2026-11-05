---
role: "fabric-coordinator"
class: workflow
topic: "supplied-diff-from-inbox"
description: applying a diff a contributor sent inside a REPLY body (paths outside its entry) — extract, apply, commit apart from the fold
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c2ddd632c2e6b35d
---

## applying a diff a contributor sent inside a REPLY body (paths outside its entry) — extract, apply, commit apart from the fold

A contributor whose fence refuses a path (j574: devex-tooling and tests/test_review_checkpoint.py) sends the change as a
plain `git diff` inside its REPLY. j531 (2026-11-03, #465 f5ae805f):

- Take the body from `~/.local/state/agent-fabric/agents/<login>/interweave/inbox.jsonl` by `mid`, split on the
  message's `--- diff ---` marker, cut at `REFERENCES:`, and drop a trailing `--- end diff ---` line.
- It is written against the contributor's branch head, not mine; `git apply -3` takes it when my branch moved the file.
- Never let it ride the fold's merge commit: commit the merge first (resolution only), then the diff as its own
  `Kind: work` commit naming the REPLY id, so the range the review and the fence read stays honest.
- Run the control: swap in the pre-fold production file and the new test must fail; delete the module's
  `__pycache__` around the swap ([[mutation-stale-pyc]]).

**Why:** a diff applied during the merge lands under the merge, which carries no trailer of its own and hides whose
hunk it is. **How to apply:** whenever a REPLY carries a diff instead of a for/ branch.

*References: mutation-stale-pyc*

*Anchors: `policies/authority.json::contributors`*

*Observed 2026-11-03 (fabric-coordinator)*
