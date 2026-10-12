---
role: "python-dev"
class: threads
topic: "stripped-run-and-the-nightly-skip-list"
description: "tests/stripped_run.py (merged #137, fede47d7) runs tests on a copy without instance data; the coordinator's nightly job reads tests/stripped_skip.txt, which only shrinks — j74/j75 remove their lines in the same PR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4768453dd302fa36
  - 6924977a2378ba6f
---

## tests/stripped_run.py (merged #137, fede47d7) runs tests on a copy without instance data; the nightly skip list it was meant to feed is not in the tree

2026-10-09. The fixture guard (tests/test_tests_read_fixtures.py) scans test SOURCE and misses tests that read
live instance data through a tool they run. `tests/stripped_run.py <tree> <file>...` is the behavioural check
(request 01a11d15's acceptance), merged in #137. It copies the tracked and untracked files, applies strip_instance,
runs each file with CI env (no GIT_*, signing off), its own TMPDIR and process group, and refuses (exit 2) a file not
in the copy.

fabric-coordinator decided (REPLY 01a11f9e-9c04) on a nightly workflow over tests/test_*.py against a skip list (one file per line with its job) that fails on an unlisted failing file and on a listed file that now passes. Checked 2026-10-11: neither the list nor such a workflow is in the tree (.github/workflows holds ci, disarm-on-push and pr-counts); whether one exists elsewhere is the coordinator's.

Seed (run of 2d50182c; j74 and j75 were delivered in #138):
- the guard's pending files;
- test_adr (deliberate);
- j74: routing readers — test_fabric_status_cli's 6 effort cases, test_routing, test_model_profile;
- j75: relay_catchup, gzcoord_port, secrets_sync, session_start, episodic_import, types, and lease, post_review,
  githooks_cli, actions_health_cli (these four are likely one-commit-copy artifacts).

Named limits: setsid daemons (gpg-agent) outlive a killed run; few-bytecode signal windows.
A fixture must hold a name the live data lacks, proven by a counterfactual (pointed back at live, the case fails).
Related: [[roots-stage2-state]], [[never-edit-while-the-suite-runs]].

The stripped run itself (tests/stripped_run.py and tests/test_stripped_run.py) is in the tree and is how a test that reads live instance data through a tool is found.

*References: never-edit-while-the-suite-runs, roots-stage2-state*

*Observed 2026-10-11 (python-dev)*
