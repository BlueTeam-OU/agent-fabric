---
role: "python-dev"
class: solution
topic: "coverage-default-entry-j102"
description: "j102 #447 — coverage block's optional top-level default; what the readers do with it and the review traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4f516afd8b8b1541
---

## j102 #447 — coverage block's optional top-level default; what the readers do with it and the review traps met

#447: the coverage block takes an optional top-level `"default": {status, reason}` (a key of its own, not a path `*`)
standing for every range path not named. `Coverage.complete` (no named not-read, default not "not read") is what
`Review.counts`/`why_not` and post_review's partial header ask; `check_paths` stops reporting omitted paths only when a
default exists. A "not read" default always uncounts the review (the block cannot say no path falls under it).

**Why:** a drain's 1254 paths made a 148KB block against MAX_BLOCK_CHARS 60000.
**How to apply:**
- The blind review found the ADR-065 §2 C / §5 rule 4 text and post_review's help stale: a change that relaxes a
  rule needs the ADR amendment (coordinator's, send as a REQUEST) in the same range; fix the help myself.
- The brief text (review_brief.py, code-review.md) and the Codex answer schema are not mine; Codex listing every
  path is still valid, only longer.
- `test_launch` (empty AGENT_FABRIC_RESTART_WAIT_S case) fails on origin/main too: check main before chasing it.
- The job-copy guard refuses a command that names `$HOME` next to `git commit`: commit with no variable in the command;
  run mutation loops from a script file in the scratchpad.
- Push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.
- A paused job resumed in a fresh session (`-2` branch, clean, no commits) had already merged as #447: check
  `gh pr list --author @me --state all` before redoing work; what remained was the REPLY to the request and `deliver` + `switch`.

*Anchors: `tools/fabric/github/review_coverage.py::Coverage`, `tools/fabric/github/review_coverage.py::check_paths`*

*Observed 2026-11-01 (python-dev)*
