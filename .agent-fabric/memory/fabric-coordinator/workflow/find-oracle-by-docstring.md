---
role: "fabric-coordinator"
class: workflow
topic: "find-oracle-by-docstring"
description: "Before asking for a port's oracle, grep tests/ for the bash file's path in docstrings, not for a matching test file name: Wave 9 oracles are named test_policy_*, test_githook_* etc."
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 26925197c00afa6b
---

## Before asking for a port's oracle, grep tests/ for the bash file's path in docstrings, not for a matching test file name: Wave 9 oracles are named test_policy_*, test_githook_* etc.

2026-10-19: I judged two Wave 9 batch 3 oracles missing because no tests/test_<bashname>.py
existed, and asked python-dev-03 for one and a subagent for another. Both already existed as
tests/test_policy_model_pins_check.py and tests/test_policy_dir_authority_entry.py (dd0a6220),
each saying in its docstring "policies/test_<...>.sh, case for case". The subagent's duplicate
was dropped and python-dev-03's request corrected (REPLY 01a15490).

**Why:** ports name their oracle by what it tests, not after the bash test it replaces.

Again the same day: I asked python-dev-04 (j55, #327) to port tests/test_leak-check.sh, and
tests/test_leak_check.py (231653f6, merged with #322) already held it case for case — a second
oracle of one file; corrected by REPLY 01a15527.

**How to apply:** `git grep -ln '<bash path>' origin/main -- 'tests/*.py'` (and `case for case`) before deciding an
oracle or a port is missing or dispatching anyone to write one — every time, including when the
inventory row still lists the bash file (the inventory is the wave as decided, not its state).
Related: [[data-and-reader-together]].

*References: data-and-reader-together*

*Anchors: `tests/test_policy_dir_authority_entry.py::case for case`, `docs/wave-9/inventory.md::## Ports`*

*Observed 2026-10-19 (fabric-coordinator)*
