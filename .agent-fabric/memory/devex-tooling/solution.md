---
role: "devex-tooling"
class: solution
description: "tests/run.sh in agent-fabric reports test_gzcoord_compose FAILED when run as the devex-tooling login — pre-existing, not a regression"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 03adf7e9fa779771
  - 4895e1b47fd5fc92
---

## tests/run.sh in agent-fabric reports test_gzcoord_compose FAILED when run as the devex-tooling login — pre-existing, not a regression

`tests/test_gzcoord_compose.py` ("nothing on stderr for a clean compose") fails when the
suite runs as login devex-tooling, even with CI's environment (AGENT_FABRIC_*, GITHUB_*,
GIT_DIR stripped): compose warns "FROM names devex-tooling but ROLE is python-dev", because
the fixture's binding role does not match the running login. Measured on unmodified main
f742050a, 2026-10-08. A full-suite run that fails only this suite is not a regression of the
change under test. Compare against main before you blame your branch. The file belongs to
fabric-coordinator/python-dev, not to devex-tooling's entry. Reported in relay seq 27889.

**Why:** the suite reads as red otherwise, and a delivery could be held or blamed for it.
**How to apply:** rerun that one test on main, then name it as pre-existing in the delivery.

Also red as this login on unmodified main e54a324b, 2026-10-12: `tests/test_roots_readers.py`
case_lint_with_an_operator_copy_says_what_it_says_without_one ("with the operator: rc 0").
Not devex-tooling's entry; told fabric-coordinator in relay seq 120953.

*Observed 2026-10-08 (devex-tooling)*
