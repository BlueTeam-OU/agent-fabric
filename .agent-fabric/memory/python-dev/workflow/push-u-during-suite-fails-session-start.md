---
role: "python-dev"
class: workflow
topic: "push-u-during-suite-fails-session-start"
description: "git push -u while tests/run.sh runs changes the clone's git config and fails test_session_start; rerun that suite alone"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 837538783d65b94f
---

## git push -u while tests/run.sh runs changes the clone's git config and fails test_session_start; rerun that suite alone

j91 (#474): a full run started before `git push -u` ended with one failed
suite, `tests/test_session_start.py` ("the running clone's git config
changed"): the push wrote branch upstream keys into the config mid-run.

**Why:** the suite snapshots the clone's config at start and compares at end.

**How to apply:** push (and commit, if hooks touch config) before starting the
full run, or after it ends; if it already failed so, rerun that suite alone
with CI's env stripped and say so in the arm basis. Also: a queued
`tests/run.sh` waits on the host lease (here ~1 h), so start it early.
Review traps: `fabric-review next` needs the request's `range` as full shas.

*Anchors: `tests/test_session_start.py::the running clones git config changed`*

*Observed 2026-11-04 (python-dev)*
