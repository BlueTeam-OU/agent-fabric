---
role: "python-dev"
class: workflow
topic: "post-review-needs-a-file-the-owner-can-run"
description: "classifier denies the agent posting a hand-copied review report; the owner runs `! fabric-pr post-review N --head SHA < file`, and the file must exist first"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4b44ceb609f94a34
---

## classifier denies the agent posting a hand-copied review report; the owner runs `! fabric-pr post-review N --head SHA < file`, and the file must exist first

The review class's report reaches the session only as a handback message, and the subagent transcript does not hold it. Posting a copy the agent typed itself is denied by the auto-mode classifier as self-approval (twice, j179 #406), whatever "merge N" the owner said.

**Why:** the agent would be vouching for its own transcription of the review.

**How to apply:** write the report to the scratchpad with the Write tool (never in the same Bash command as the post: a denial then leaves no file), give the owner one line `! fabric-pr post-review N --model claude --head <full sha> < <absolute path>` with no placeholders, then re-read the gate and `fabric-pr arm N --basis "the owner's word: ..."`. A boundary file at 1 work commit armed on the owner's word without an AUTHORIZES id. See [[arm-under-8-boundary-needs-owners-word-phrase]].

*References: arm-under-8-boundary-needs-owners-word-phrase*

*Anchors: `tools/fabric/github/post_review.py::REVIEW_MARKER`*

*Observed 2026-10-28 (python-dev)*
