---
role: "python-dev"
class: workflow
topic: "gzcoord-backfill-j134-resume"
description: "j134 #573 gzcoord backfill — MERGED 2026-11-13 at e4abdf74; review-count traps (partial coverage, merge in range), fixed-date time bomb, managed snapshot routing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fda58152bc36eeff
---

## j134 #573 gzcoord backfill — MERGED 2026-11-13 at e4abdf74; review-count traps (partial coverage, merge in range), fixed-date time bomb, managed snapshot routing

j134 (#573, `tools/fabric/gzcoord/backfill.py` + agentd 60 s Ticker) and j136 (no SyntaxWarning rule) merged 2026-11-13 at head e4abdf74 (5 work, 3 fix, 2 merge), armed below the minimum on the owner's DECISION with AUTHORIZES + `--authorization <id>`. Fabric-coordinator owns distribution and the live read-back (its j811).

**Traps, each cost a round:**
- A re-review of a boundary PR must COUNT: a report whose coverage block says `default: not read` (the merge's 109 paths) is recorded as *partial* and `fabric-pr arm` refuses ("no review-class review of the current head"). After a merge of main the config hash may differ, and `fabric-review brief` then refuses a re-review ("no review a re-review can start from"): render `mode: review` over `merge-base(origin/main)..head`, which after a merge is only the PR's own files. Merge main BEFORE the review round that will be last.
- `fabric-review next` says "head has not moved" when a prior `next` already recorded the head; use `fabric-review brief REQUEST.json` directly. `fabric-pr post-review` wants the dispatch block first and NO review-marker line; bare command only (no `2>&1`, no `cd &&`).
- Fixed-date time bomb in my own test: `tick()` reads the real clock, a row dated from a fixed T0 crossed the 12 h bound and CI (debian) went red the next day. Date rows from `datetime.now` in tests that call code with no clock seam; proof = row 900 min old reproduces the CI failure.
- Review dispatch was refused ("effort high vs medium") because the managed snapshot under /usr/local/lib/agent-fabric/managed/ routed code-review at medium; only the owner's root reinstall fixed it, no relaunch. Coordinator confirms; ask them, do not retry.
- `git push` needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin HEAD`; `fabric-jobs done` wants `BlueTeam-OU/agent-fabric#N`, not `pr:N`; `done` takes active/delivered only (start a queued job first).
- Own lint in this checkout flagged stale docs/adr index files that the reviewer's head worktree did not: coordinator's, not mine.

*Anchors: `tools/fabric/gzcoord/backfill.py::MAX_AGE_S`, `tests/test_gzcoord_backfill.py::tick uses the token it is given`*

*Observed 2026-11-13 (python-dev)*
