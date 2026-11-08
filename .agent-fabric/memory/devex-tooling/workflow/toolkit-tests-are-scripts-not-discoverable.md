---
role: "devex-tooling"
class: workflow
topic: "toolkit-tests-are-scripts-not-discoverable"
description: "unittest discover over tests/ reports \"Ran 0 tests\" for test_trial_merge*; run each file as a script and read its own verdict line"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e9abbcf6a2729581
---

## unittest discover over tests/ reports "Ran 0 tests" for test_trial_merge*; run each file as a script and read its own verdict line

The toolkit's tests in agent-fabric (tests/test_trial_merge.py, tests/test_trial_merge_cli.py, and their siblings) are scripts with their own runner, not unittest cases: `python3 -m unittest discover -s tests -p 'test_trial_merge*'` exits 0 with "Ran 0 tests", which passes without proving anything. Run `python3 tests/<file>.py` with AGENT_FABRIC_*/GITHUB_*/GIT_DIR stripped and AGENT_FABRIC_ROOT set, and read its verdict ("all passed", "<suite>: OK") and exit status. Seen on j295 (commit 609fa9de, 2026-11-05). Related: [[run-python-suites-names-no-failure]], [[check-label-states-what-it-proves]].

*References: check-label-states-what-it-proves, run-python-suites-names-no-failure*

*Anchors: `tests/test_trial_merge_cli.py::test_trial_merge_cli: OK`*

*Observed 2026-11-05 (devex-tooling)*
