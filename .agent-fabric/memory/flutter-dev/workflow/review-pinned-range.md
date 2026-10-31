---
role: "flutter-dev"
class: workflow
topic: "review-pinned-range"
description: "A review that should count on a PR must be of a pushed range (pinned); a diff-file review cannot be posted, and Codex needs card_base when the range starts on a branch merge"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 16ee06449cd52b3f
---

## A review that should count on a PR must be of a pushed range (pinned); a diff-file review cannot be posted, and Codex needs card_base when the range starts on a branch merge

On gzapp #1138 (2026-10-20), round 4's review-class review was briefed with a `diff:` file (`evidence_mode: working-tree`), and `fabric-pr post-review` refused it: only a pinned review covers a head (agent-fabric ADR-020 §5 rule 10). Codex refused the same brief because it reviews only a pushed range. With a `range:` starting at a merge commit on the branch (not on main), `fabric-review` also refuses until the request names `card_base:` (a full commit id main contains); the review card is read from there.

**Why:** a working-tree review costs a full reviewer run and then cannot reach the gate.

**How to apply:** push first, then brief both engines with `range: <base>..<head>` and, when the base is a branch merge, `card_base: <full sha on main>`. Also: `dart format` on gzapp passenger rewrites files the change never touched (the workstation formatter differs from the tree's style, and CI has no format gate); do not run it on a commit. See [[flutter-safe-directory]].

*References: flutter-safe-directory*

*Anchors: `runtime/claude-code/review/README.md::card_base`*

*Observed 2026-10-20 (flutter-dev)*
