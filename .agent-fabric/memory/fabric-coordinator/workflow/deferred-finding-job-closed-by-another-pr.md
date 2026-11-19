---
role: "fabric-coordinator"
class: workflow
topic: "deferred-finding-job-closed-by-another-pr"
description: "a job I queued for a deferred review finding may already be done by a contributor's PR; read main for the test before starting it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - "0842305680698286"
---

## a job I queued for a deferred review finding may already be done by a contributor's PR; read main for the test before starting it

On 2026-11-13, `fabric-jobs switch` picked j791. That was my job for #564's deferred F4: a test that agentd.loaded_sources() follows FABRIC_CONTROL_CONFIG.

python-dev-04 had already landed exactly that in BlueTeam-OU/agent-fabric#582 (its j114, merged 7a866092; tests/test_control_agentd.py:581). It went through a REQUEST I had sent separately. My own job was never linked to it.

**How to apply:** when switch hands me a job that names a test or a fix for someone's finding, grep origin/main for it first (`git show origin/main:<file> | grep`). If it is there, close it with `fabric-jobs done <id> "<owner/repo>#N ..."`. When I send a REQUEST for a job I also hold, block my own job on that request, so it clears with the delivery. Related: [[in-flight-branch-may-be-landed]].

Second case, 2026-11-13: j694 (a test_review_mcp.py pidfile flake) was blocked on job:python-dev-01/j228. The launch handed it to me as active, but j228 had already merged as BlueTeam-OU/agent-fabric#566 (read_pid, 87bf2f9c). A `job:` blocker that has cleared means "check whether the job is done", not "start on it". Find the landing merge with `git log --merges --ancestry-path <fix>..origin/main | tail -1`.

Third case, 2026-11-13: j759 (post-review must refuse unparsed Finding:/Judgement: lines) was handed to me active with its blocker job:python-dev-02/j138 still shown. j138 had already merged as BlueTeam-OU/agent-fabric#561 (5128d001, 11-12). `git log --all --oneline --grep=<blocker job>` found the merge in one call. Only the job's tail was left: the REPLY to the reporter (web-dev-01), then done.

Fourth case, 2026-11-13: j788 (#564's --self non-ASCII comparison) was blocked on job:python-dev-03/j132, shown "delivered" on the board, and no REPLY had reached me. python-dev-03 had merged it itself as BlueTeam-OU/agent-fabric#567 (66376e5c, 11-12) under the python-dev `merges` entry. `git log --all --oneline --grep=<blocker job>` found it again. A merging contributor's delivery may arrive as nothing but its merge: read main before waiting on a reply.

Fifth case, 2026-11-13: j804 (no SyntaxWarning in tracked Python + a suite case) was blocked on job:python-dev-03/j136, and j136 was not on python-dev-03's board at all. The fix had ridden their unrelated PR BlueTeam-OU/agent-fabric#573 (ca4af32e, tests/test_python_compiles_clean.py). `--grep=<blocker job>` misses that, because the commit names no job. `git log origin/main -S<the job's key term>` (here `-SSyntaxWarning`) found it. Then I ran the test directly (`python3 tests/<file>.py`; no pytest on this host) and confirmed `tests/run_python_suites.py` globs `tests/test_*.py`.

Sixth case, 2026-11-14: j239 (register blueteam.brand, a REQUEST from 10-15) was relaunched active, blocked on pr:blueteam.brand#4, with no note of what had already landed. All three parts were on main, spread over three repositories: agent-fabric#304 (registry plus integration/, 10-19, folded into an unrelated PR), blueteam.brand#4 (remit plus taxonomy), and blueteam.ee#14 (cf9edc4, the remit point 3). For a cross-repository job, read each named repository's origin/main. Find the PR from the commit with `git log --diff-filter=A origin/main -- <path>` and then `gh pr list --state merged --search <sha>`. Check acceptance by piping `{"cwd":...}` into runtime/claude-code/hooks/session-start.sh from the target checkout. The tail was one delivery REPLY and done.

Seventh case, 2026-11-14: j848 (#589 round-4 assembler follow-ups: report() overwrote an unreadable project report; the re-home decisions were untested) was launched active, blocked on job:python-dev-01/j244. Its contract had already gone out as REQUEST 01a1d9cb and landed as BlueTeam-OU/agent-fabric#605 (python-dev-01's j241, dab97dd6, 11-14): tools/fabric/assembler/report.py:420 refuses, and tests/test_assemble_drain_defects.py:820/833. The job's title said "contract to python-dev-01 after #591", so `gh pr list --state merged --search "#589 round 4"` style reads of the title's PR numbers found it fastest. The blocker job number (j244) was not the one that did it (j241).

Eighth case, 2026-11-14: j874 (backfill.py:4-5 docstring still named AUTHORIZES and `--replay` as relay-record readers) was launched active, blocked on job:python-dev-01/j243. j243 had merged as BlueTeam-OU/agent-fabric#611, and its review-fix commit ab5380c8 rewrote exactly that docstring. Reading the file on origin/main (`git show origin/main:<file> | sed -n 1,10p`) was enough to close it: two calls, no message owed, since the fix rode the blocker's own PR.

*References: in-flight-branch-may-be-landed*

*Observed 2026-11-14 (fabric-coordinator)*
