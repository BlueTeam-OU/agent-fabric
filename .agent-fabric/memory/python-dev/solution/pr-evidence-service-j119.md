---
role: "python-dev"
class: solution
topic: "pr-evidence-service-j119"
description: "j119 #513 — PR files/commits read once through github/evidence.py; arm.json hunk, review-round traps, guard and git traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 50879c99b263c665
---

## j119 #513 — PR files/commits read once through github/evidence.py; arm.json hunk, review-round traps, guard and git traps

PR file and commit lists are read only through `tools/fabric/github/evidence.py` (`PrEvidence.files/commits/has_commit`; `Incomplete` at `common.PR_FILE_LIST_CAP` 3000 / `PR_COMMIT_LIST_CAP` 250). `tools/fabric/evidence_caps.py` is the checker (state_writes pattern; wiring is the coordinator's). `Incomplete.partial` exists for results.py alone, which says a PR was "read in part".

Traps met:
- A new module in arm.py's import closure turns `tests/test_arm_fabric_config.py` red until `arm.json` names it; that file is the coordinator's, so send the two edits in the REPLY and they commit onto the branch (see [[new-agent-suite-execs-and-sweep-roots-j73-j74]]). Do not push until their REPLY.
- `tests/test_post_review_cli.py`'s fake gh matched `api --paginate --slurp <path>` by position; moving reads to `gh.api` changed the argv order (`api <path> --method GET --paginate --slurp`), so the fake needed an either-order match.
- A mutation loop that ends in `git checkout -- file` destroys an uncommitted fix to that same file: commit first, then mutate.
- The PreToolUse guard refuses a command that mixes `git commit`/`git push` with `$HOME`/`$PATH` expansion; commit and push in their own calls.
- A caught `TypeError` in review_checkpoint makes the `isinstance(..., Incomplete)` mutation equivalent (survives); say so rather than chase it.
- `fabric-review next` needs the round saved first (`fabric-review save N R < report`), and for round 3 the REQUEST is the `req-rr<N>.json` it wrote, not the original.
- Editing the tree while `tests/run.sh` runs (or waits on the full-suite lease) taints it: stop the run, fix, restart.

**Why:** cost four review heads (a P3 per round), two restarted suites. **How to apply:** fix known P3s and comments before the review that will be posted; one commit per call; arm with `--authorization <id> --defer "<head8>:F<n>" "<why>"` when the coordinator names it.

*References: new-agent-suite-execs-and-sweep-roots-j73-j74*

*Anchors: `tools/fabric/github/evidence.py::PrEvidence`, `tools/fabric/evidence_caps.py::scan`, `tools/fabric/github/common.py::PR_COMMIT_LIST_CAP`*

*Observed 2026-11-08 (python-dev)*
