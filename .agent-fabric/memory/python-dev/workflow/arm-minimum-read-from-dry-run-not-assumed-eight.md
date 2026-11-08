---
role: "python-dev"
class: workflow
topic: "arm-minimum-read-from-dry-run-not-assumed-eight"
description: "j89 #463 — the arm minimum was 1 work commit, not the 8 I assumed; read `fabric-pr arm --dry-run N --basis x`, and count work/fix from `fabric-pr gate`"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a45887298bcaabea
---

## j89 #463 — the arm minimum was 1 work commit, not the 8 I assumed; read `fabric-pr arm --dry-run N --basis x`, and count work/fix from `fabric-pr gate`

In j89 I told the owner twice that #463 "probably needs 8 work commits" and
quoted counts from my own commit list (5 work, 6 work). `fabric-pr gate 463`
said 4 work, 2 fix, and `arm --dry-run 463 --basis "dry run"` said "count rule:
4 work commits — 1 or more, arms at the review gate". Armed it myself.

**Why:** the stop hook (pr-counts.py) refuses any status line without
"#N (W work, F fix)" read from gate; a guessed minimum cost two wrong statements.

**How to apply:** after the first push run gate and the dry-run (it refuses
without --basis; any text works for a dry run) before saying anything about
arming. Review-fix commits stamped `Answers:` count as fix, not work.
Also: `fabric-review next` writes req-*.json beside the request and prints the
brief; save the round first with `fabric-review save N R < report` (no --repo).

*Anchors: `tools/fabric/github/arm.py::AUTHORIZES`*

*Observed 2026-11-03 (python-dev)*
