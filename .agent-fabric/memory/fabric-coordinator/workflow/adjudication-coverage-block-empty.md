---
role: "fabric-coordinator"
class: workflow
topic: "adjudication-coverage-block-empty"
description: "post-review refuses a finding-adjudication report whose coverage block names any path — an H..H range is empty, so \"paths\" must be {}"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 33dc1e9709857a40
---

## post-review refuses a finding-adjudication report whose coverage block names any path — an H..H range is empty, so "paths" must be {}

A finding-adjudication runs on an H..H range (see [[adjudication-range-is-head-to-head]]), whose
`git diff --name-only` is empty. `fabric-pr post-review` then refuses any coverage block that names a
path: "the coverage block names N path(s) outside the range". The reviewer naturally lists the files it
read, so tell it in the brief, or ask it afterwards, to carry `"paths": {}` with a `"default"` entry and
the lens line. Seen on agent-fabric #545 (j719, 2026-11-10): the reviewer reissued the block unchanged
otherwise and the second post went through.

Also: the adjudication brief carries no findings by itself unless the request names them; put the
round's `Finding:` lines into `requirements` ("To judge: Finding: F1 | …"), since the reviewer
cannot read the PR from GitHub.

Related: a Bash call whose text contains the words "fabric-pr post-review" (even inside a quoted
heredoc of an edit script) is stopped by the post-review hook; put such scripts in a file.

*References: adjudication-range-is-head-to-head*

*Anchors: `tools/fabric/github/post_review.py::a path outside the range`*

*Observed 2026-11-10 (fabric-coordinator)*
