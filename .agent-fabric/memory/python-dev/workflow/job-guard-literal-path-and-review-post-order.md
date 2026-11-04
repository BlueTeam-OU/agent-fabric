---
role: "python-dev"
class: workflow
topic: "job-guard-literal-path-and-review-post-order"
description: "commit/push in a job worktree needs the literal path, alone; re-review needs the first review posted verbatim first"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 33f98073677ca68e
---

## commit/push in a job worktree needs the literal path, alone; re-review needs the first review posted verbatim first

Working a job in its worktree from the main checkout (j183, #414):

- The job guard resolves only a literal `git -C <path>` or `cd <path>`; a `$VAR`, a `$TMPDIR` anywhere in the same command, or a commit chained after other work reads as "outside" and is refused. Run each `git commit` / `git push` as its own command with the literal path.
- `fabric-review brief` for a re-review is refused until the first review is posted (`fabric-pr post-review <n> --model fable --head <sha>`, body from stdin). The posted body must be the reviewer's report verbatim: write it from the hand-back text, not a condensed copy. Drop `previous_findings:` from the request; the brief reads it from the posted review.
- `fabric-pr arm` on a security-boundary file with one work commit: a review of the head first, then the owner's word ("merge" from the owner counts) in `--basis`; wait-merged then ends on MERGED.

**Why:** each of these cost a refused call or a rewritten file.
**How to apply:** literal path, one command; post review before the re-review brief. See [[post-review-needs-a-file-the-owner-can-run]].

*References: post-review-needs-a-file-the-owner-can-run*

*Anchors: `tools/fabric/review_brief.py::has no review a re-review can start from`*

*Observed 2026-10-28 (python-dev)*
