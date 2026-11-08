---
role: "backend-dev"
class: workflow
topic: "fabric-review-rereview-card-base"
description: "Writing a fabric-review brief request — a PR's re-review gives pr + range from the last posted review's head, and NO previous_findings or card_base (both read from that review); card_base only for a PR-less ranged request whose base is…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 68d96345d39a0bc3
---

## Writing a fabric-review brief request — a PR's re-review gives pr + range from the last posted review's head, and NO previous_findings or card_base (both read from that review); card_base only for a PR-less ranged request whose base is off main

How `fabric-review brief` takes a request, read in tools/fabric/review_brief.py at
agent-fabric origin/main 0c0938d4 (ADR-065 §5 rule 5):

- **A PR's re-review** (`mode: re-review` with `pr:`). It starts from the PR's last posted
  v2 review, the checkpoint. The range must be `<that review's head>..<new head>`, and
  any other base is refused with the range it expects. `previous_findings` is refused
  ("reads the previous report from its last posted review; leave previous_findings
  out"). `card_base` is taken from the checkpoint, and a typed one that disagrees is
  refused, so leave it out. With no checkpoint (no posted v2 review of an ancestor under
  today's config), render a full `mode: review` instead.
- **A ranged request with no PR.** `card_base` is optional and must be a full commit id
  that the default branch contains. When the range's base is a branch commit not on
  main, the brief refuses ("name card_base … the first round's base"). A PR-less
  re-review still needs `previous_findings`, a file.
- **`mode: finding-adjudication`.** `previous_findings` is the file naming the findings
  to judge.
- These still hold: `repository:` is the working copy's PATH, not owner/repo.
  `threat_model` (like requirements, invariants, scope) is a list. `objective` is
  required on everything except a re-review. Free text that explains a defect is refused
  as rationale (`--allow-rationale` renders it flagged).

**Why:** each refusal costs a render cycle mid-review-loop. I first learned this on gzapp
#1142 (2026-10-19), when a typed card_base and previous_findings were the way to do it.
ADR-065's checkpoint replaced that flow, and the 2026-10-31 drain held out the old
memory for teaching it.

**How to apply:** for a PR's re-review, write only mode, pr, repository, range (from
the last posted review's head) and evidence, and let the brief read the rest. If it
refuses, use the range its refusal names. Related: [[review-coverage-needs-pinned-evidence]].

*References: review-coverage-needs-pinned-evidence*

*Anchors: `agent-fabric:tools/fabric/review_brief.py::card_base`*

*Observed 2026-10-31 (backend-dev)*
