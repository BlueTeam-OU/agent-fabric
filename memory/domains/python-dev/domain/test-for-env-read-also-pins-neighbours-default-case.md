---
role: "python-dev"
class: domain
topic: "test-for-env-read-also-pins-neighbours-default-case"
description: "adding a test for an env-var override: the neighbouring default-case test silently reads the session's variable; pin it in the same change"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 184dba80d483a605
---

## adding a test for an env-var override: the neighbouring default-case test silently reads the session's variable; pin it in the same change

When a function reads an env var with a default fallback (`os.environ.get(X) or DEFAULT`), the existing "default" test passes only because the variable is unset. j114 (#582): the review found `test_port_the_files_watched_...` failed with `FABRIC_CONTROL_CONFIG` exported, which the new override case did not show.

**Why:** the review class judges the brief's invariant "does not depend on the session's environment" against the neighbours, not only the new case; a pre-existing hole one line away is fixed in the same PR, not carried.

**How to apply:** after writing the override case, run the whole class with the variable exported to a bogus path (`env X=/nonexistent python3 -m unittest ... -k <area>`), and pin the default case with `mock.patch.dict(os.environ, {X: ""})`. Also: a fixture file that the code under test only names (never opens) is not needed; `open(p, "w").write(...)` leaves a ResourceWarning. Related: [[mutation-run-read-rc-not-fail-count]].

*References: mutation-run-read-rc-not-fail-count*

*Observed 2026-11-13 (python-dev)*
