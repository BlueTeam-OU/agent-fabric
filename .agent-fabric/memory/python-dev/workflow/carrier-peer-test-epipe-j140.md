---
role: "python-dev"
class: workflow
topic: "carrier-peer-test-epipe-j140"
description: "j140 #599 - a test that sends to a peer the server closes at accept must expect EPIPE; reads_live is a fixture; how the review base and arming went"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b78299ff8abb32d0
---

## j140 #599 - a test that sends to a peer the server closes at accept must expect EPIPE; reads_live is a fixture; how the review base and arming went

A socket test that sends to a peer the server closes unread (control_link `_serve`, stranger uid) races: close before send gives BrokenPipeError at `sendall`. Catch it around `sendall` only and still `recv`, so a refusal written before the close stays readable (a mutant writing one still fails). Repro under 24 busy loops, 150 runs: 4-9 failures on main and its parent, 0 fixed (#599, merged).

`tests/test_reads_live.py` is never tracked: `tests/test_stripped_run.py` writes it into a scratch tree; its `FAILED (exit 1)` line is an expected case. A CI log's real failure is the suite named before `FAILED_SUITES=` (here test_run's group-INT case, coordinator's lane, observation sent).

**Why:** the requester's premise ("file removed") was wrong; the log said otherwise.
**How to apply:** grep a CI log for the `: 1 FAILED` / `FAIL ` lines of the suite, not the file named in a request. `fabric-pr post-review` refuses a report whose base is not an ancestor of head: merge main into the branch first, then re-render the brief and review the new head. Below-minimum arming needed no `--authorization` here (count rule said 1 work commit arms at the gate). A `cd` into the scratchpad before gzcoord-send trips the one-job-copy hook; use absolute paths.

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::_serve`, `tests/test_stripped_run.py::READS_LIVE`*

*Observed 2026-11-14 (python-dev)*
