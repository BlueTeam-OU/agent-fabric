---
role: "devex-tooling"
class: workflow
topic: "launch-cli-gateway-timeout-flake"
description: test_launch_cli, test_gzcoord_protocol, test_cpu_lease, test_post_review_shape_guard, test_leak_check, test_shim can FAIL in a full tests/run.sh under load and pass alone
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4c3a3a525634d95c
  - 81b8c31810034845
  - bff7da192272d014
---

## test_launch_cli, test_gzcoord_protocol, test_cpu_lease, test_post_review_shape_guard, test_leak_check, test_shim can FAIL in a full tests/run.sh under load and pass alone

In a full `tests/run.sh` (CI env, 2026-10-15, j134), `tests/test_launch_cli.py` group 8 failed one check: "a gateway that never answers the ask does not hold the end of the session". Rerun alone, it passed on the branch and on a clean origin/main worktree. Before calling it a regression, rerun the suite alone, at base and on the branch. Parse the `==` blocks to find which suite failed ([[run-python-suites-names-no-failure]]). The other usual local red in the same run is corpus lint on sibling index drift ([[lint-no-siblings-for-own-tree]]).

Seen again 2026-10-16 (j137): FAILED_SUITES=2 were test_launch_cli (group 6, 3 checks; group 8, 1) and test_gzcoord_protocol (1 of 105 cases); both passed alone on the branch and on origin/main. A `tests/test_reads_live.py: FAILED` line in the same output is test_stripped_run's fixture, not a suite.

Seen again 2026-11-05 (j294, a14af9b2): FAILED_SUITES=2 with failing cases in test_cpu_lease (third taker), test_post_review_shape_guard ("fast: 100 000 nested evals" timing), test_leak_check (4 RunLeaves cases) and test_shim; each passed run alone on the branch, whose diff touched only arm.py and test_arm_cli.

*References: lint-no-siblings-for-own-tree, run-python-suites-names-no-failure*

*Observed 2026-11-05 (devex-tooling)*
