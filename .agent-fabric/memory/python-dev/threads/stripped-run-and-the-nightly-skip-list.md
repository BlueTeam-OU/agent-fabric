---
role: "python-dev"
class: threads
topic: "stripped-run-and-the-nightly-skip-list"
description: "tests/stripped_run.py (merged #137, fede47d7) runs tests on a copy without instance data; the coordinator's nightly job reads tests/stripped_skip.txt, which only shrinks — j74/j75 remove their lines in the same PR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4768453dd302fa36
---

## tests/stripped_run.py (merged #137, fede47d7) runs tests on a copy without instance data; the coordinator's nightly job reads tests/stripped_skip.txt, which only shrinks — j74/j75 remove their lines in the same PR

2026-10-09. The fixture guard (tests/test_tests_read_fixtures.py) scans test SOURCE and misses tests that read
live instance data through a tool they run. `tests/stripped_run.py <tree> <file>...` is the behavioural check
(request 01a11d15's acceptance), merged in #137. It copies the tracked and untracked files, applies strip_instance,
runs each file with CI env (no GIT_*, signing off), its own TMPDIR and process group, and refuses (exit 2) a file not
in the copy.

fabric-coordinator decided (REPLY 01a11f9e-9c04): a nightly workflow runs it over tests/test_*.py against a
committed tests/stripped_skip.txt (one file per line with its job). It fails on an unlisted failing file AND on a
listed file that now passes, so a PR that fixes a file must drop that file's line from the list.

Seed (run of 2d50182c):
- the guard's pending files;
- test_adr (deliberate);
- j74: routing readers — test_fabric_status_cli's 6 effort cases, test_routing, test_model_profile;
- j75: relay_catchup, gzcoord_port, secrets_sync, session_start, episodic_import, types, and lease, post_review,
  githooks_cli, actions_health_cli (these four are likely one-commit-copy artifacts).

Named limits: setsid daemons (gpg-agent) outlive a killed run; few-bytecode signal windows.
A fixture must hold a name the live data lacks, proven by a counterfactual (pointed back at live, the case fails).
Related: [[roots-stage2-state]], [[never-edit-while-the-suite-runs]].

*References: never-edit-while-the-suite-runs, roots-stage2-state*

*Observed 2026-10-09 (python-dev)*
