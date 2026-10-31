---
role: "python-dev"
class: workflow
topic: "stripped-copy-before-push"
description: "tests/run.sh passes locally but CI's platform-smoke fails on tests that read live instance files; run touched tests through tests/stripped_run.py before pushing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 673b974aedffbcb8
---

## tests/run.sh passes locally but CI's platform-smoke fails on tests that read live instance files; run touched tests through tests/stripped_run.py before pushing

A new test that reads routing/profiles.json, runtime/hosts/registry.json or projects/registry.json passes under local `tests/run.sh` but fails CI's platform-smoke (debian, fedora) and `ci-ok`, via `test_tests_read_fixtures` case_no_test_reads_the_live_instance_files, which only runs on the stripped copy. Found on #251 (2026-10-14): the push after arming disarmed it and cost a second review round.

**Why:** the check reads the stripped copy CI uses, which the in-tree run does not.

**How to apply:** before the first push, `python3 tests/stripped_run.py . <every test file I added or touched>` under the CI environment (strip AGENT_FABRIC_*, GITHUB_*, GIT_DIR). A test that compares against an inherited module (fabric-resume) builds a fixture file and points the module at it by env; a test that calls a worker step stubs the steps it does not test. Also: a worker step added to `finish` must be stubbed in every existing finish-order test. See [[ci-env-for-lint-and-mutations]].

*References: ci-env-for-lint-and-mutations*

*Observed 2026-10-14 (python-dev)*
