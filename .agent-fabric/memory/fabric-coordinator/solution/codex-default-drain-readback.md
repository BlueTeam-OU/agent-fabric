---
role: "fabric-coordinator"
class: solution
topic: "codex-default-drain-readback"
description: "Codex review of a drain-sized range works since the coverage default (02fc6373/a1b33124); how to read it back on a merged PR without posting"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j553-live-read-back-the-first-codex"
derived_from:
  - 6b0cb327308ba614
---

## Codex review of a drain-sized range works since the coverage default (02fc6373/a1b33124); how to read it back on a merged PR without posting

2026-11-04 (j553): `bin/fabric-review --engine codex 444 <request> --gateway chatgpt --no-post` on #444's 1242-path range (00616fdf..57586b82) exited 0 in about 6 minutes. The answer named 19 paths `read` and gave a `not read` default, a 1960-byte block where #444 had failed at 162049 characters; `review_coverage.check_paths` against `diff_paths` returned "". A merged PR still takes a Codex run (`pr_head` reads the merged head); `--no-post` keeps it off the PR. The record is docs/live-checks/2026-11-04-codex-coverage-default-drain-range.md on agent-fabric #485.

The run's one P1: a personal GitHub handle the drain's hygiene substitution let through into `.agent-fabric/memory/devex-tooling/workflow/dependabot-pr-review-posters.md`, plus three slices of the same kind (job j610). Related: [[tool-note-names-project-not-owner]].

The signed commit failed once on "ots: need at least 2 attestations but received 0"; the same commit, re-run, succeeded.

*References: tool-note-names-project-not-owner*

*Anchors: `tools/fabric/github/review_coverage.py::check_paths`, `runtime/claude-code/review/codex-answer.schema.json::default`*

*Observed 2026-11-04 (fabric-coordinator)*
