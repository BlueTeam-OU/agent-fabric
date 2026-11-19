---
role: "fabric-coordinator"
class: workflow
topic: "drain-hold-dangles-links"
description: "Holding a drain claim at the bundle leaves dangling [[links]] in the admitted slices that cite it, and corpus lint stays clean; check links before choosing a hold over a fix at source"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6ebd3697ce38c116
---

## Holding a drain claim at the bundle leaves dangling [[links]] in the admitted slices that cite it, and corpus lint stays clean; check links before choosing a hold over a fix at source

On gzapp.decks#29 (j660, 2026-11-09), the review of the 2026-11-08 drain half found six brand-comms-01 claims that the tree contradicts (F8–F13). I re-assembled with `--hold` on all six. Six `[[links]]` in the admitted slices then pointed at nothing: release-attaches-pdfs, decks-repo-document-artifacts, never-stamp-a-pending-language, rationale.md, threads.md and deck-review-ledger-before-blind-findings. One of the held claims was the link target that had just fixed the PR's earlier F1. `lint.py --no-siblings` at origin/main reported clean. The assembler's log printed only a "(link): other corpus" note.

**Why:** a hold removes a slice but not the links that cite it, and lint does not report a broken `[[link]]`. Each hold can bring back the dangling-link finding a review raises.

**How to apply:** before holding, run `grep -rl "\[\[<topic>\]\]" .agent-fabric/memory` for each held topic. If anything links to it, do not hold. Send a REQUEST to the author to correct the claim at source (merge_target for a thread whose heading changed), then re-harvest that account on its own and re-assemble. On #29 I discarded the held run, answered only F3 (an orphan nothing linked to) and sent REQUEST 01a1be2d to brand-comms-01. Related: [[drain-repair-at-source-not-bundle]], [[j650-drain-2026-11-08]], [[drain-project-half-excludes-coordinator-bundle]].

*References: drain-project-half-excludes-coordinator-bundle, drain-repair-at-source-not-bundle, j650-drain-2026-11-08*

*Anchors: `tools/fabric/assemble.py::--hold`*

*Observed 2026-11-09 (fabric-coordinator)*
