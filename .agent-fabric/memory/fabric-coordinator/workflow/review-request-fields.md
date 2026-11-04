---
role: "fabric-coordinator"
class: workflow
topic: "review-request-fields"
description: "fabric-review brief request fields that refuse a render — repository is a local path, previous_findings left out of a PR re-review, a re-review needs card_base"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 19080710aa959fe2
---

## fabric-review brief request fields that refuse a render — repository is a local path, previous_findings left out of a PR re-review, a re-review needs card_base

A `bin/fabric-review brief <request.yaml>` request was refused twice on #352 (j332, 2026-10-21):
- `repository:` must be the local working copy path. An `owner/name` is refused with "not a git working copy".
- `previous_findings:` — for a PR's re-review, leave it OUT (2026-10-25, #376): the renderer reads the previous report from the PR's last posted review and refuses the field ("a PR's re-review reads the previous report from its last posted review"). It was once a file path of `Finding:` lines.
- `mode:` is `review`, `re-review` or `finding-adjudication` — never `pr` (2026-10-30, #421). The call is `bin/fabric-review brief <file>`; `brief render <file>` prints only usage, rc 2. A first-round request: mode, pr, job_id, repository, range, objective, requirements, invariants, threat_model, scope, out_of_scope, lenses (names of runtime/claude-code/review/lenses/*.md).
- `threat_model:` must be a list of `- ` items. A folded `>-` scalar is refused (2026-10-30, #425).
- A requirement that says what the code does ("X is taken after Y, in that fixed order") is refused as naming what was fixed. Write what must be true instead ("…so two runs never each hold one and wait on the other").
- More than 3 `lenses:` renders, but with a warning that the bias is diluted. Keep 3.
- In a re-review whose base is the previous head (not on main), add `card_base: <full sha of the first round's base on main>`. The review card is read from a commit main contains.

**Why:** each refusal costs a render round trip, and the skill text does not list these fields.
**How to apply:** start a re-review request from repository, range and card_base. Render it with the PR worktree's own `bin/fabric-review` ([[threads-2026-10-14-259-state]]).

*References: threads-2026-10-14-259-state*

*Anchors: `tools/fabric/review_brief.py::card_base`, `tools/fabric/review_brief.py::previous_findings`*

*Observed 2026-10-30 (fabric-coordinator)*
