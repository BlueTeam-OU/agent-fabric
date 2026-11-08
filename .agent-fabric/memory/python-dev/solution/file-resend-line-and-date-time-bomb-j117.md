---
role: "python-dev"
class: solution
topic: "file-resend-line-and-date-time-bomb-j117"
description: "j117 #507 — gzcoord-send carrier-took-it has a file line and a stdin line; test_errors.py fixed-date time bomb on 2026-11-08; a test file that does not exist reads as 0 FAIL"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c98bff4a3d7d69d
---

## j117 #507 — gzcoord-send carrier-took-it has a file line and a stdin line; test_errors.py fixed-date time bomb on 2026-11-08; a test file that does not exist reads as 0 FAIL

#507 (merged 2026-11-08, 350c77fe): when the relay did not take a message TO one login and the carrier did, `send.carrier-took-it-file` (a file resend is one message, same id) is printed for a file input, `send.carrier-took-it` (a resend would duplicate) for stdin. A stdin text that names its own MESSAGE-ID is also one message on resend, but keeps the cautious line; the comment and the test (fixture with the id stripped) say so. The three dictionary commits came onto the branch from fabric-coordinator and the language-culture holders; fast-forward to them before the next commit.

**Time bomb:** `tests/test_errors.py` stubbed `merged_prs` with a PR merged on a fixed 2026-10-25; its 14-day window closed on 2026-11-08 and the suite went red on main and in every PR (platform-smoke, then ci-ok). Fixed with a date computed from now. Grep a suite for fixed dates when it goes red on the day a window ends.

**Why:** I wrote "passes alone, not reproduced" about a `test_reads_live.py` that does not exist: the log line was a runner fixture, and `python3 tests/<missing>.py | grep -c FAIL` prints 0. A run of a missing file reads as green.

**How to apply:** find the failing case with `grep -rl "<case text>" tests` before judging a flake; run the suite's own file alone and read its rc. Protocol suite needs a short TMPDIR (AF_UNIX path). `fabric-review next` needs `card_base:` in the request and, for round 3, the previous round's generated request (`req-rrN.json`), not the original.

*Anchors: `tools/fabric/gzcoord/send.py::main`, `tests/test_errors.py`*

*Observed 2026-11-08 (python-dev)*
