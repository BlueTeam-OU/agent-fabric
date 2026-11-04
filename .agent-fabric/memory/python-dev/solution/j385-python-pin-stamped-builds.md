---
role: "python-dev"
class: solution
topic: "j385-python-pin-stamped-builds"
description: "python_pin.py installs each build in python-V+R~<16hex>; kill-matrix test with os._exit; delivered by REPLY patch, coordinator folds"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1fb63974b250429a
---

## python_pin.py installs each build in python-V+R~<16hex>; kill-matrix test with os._exit; delivered by REPLY patch, coordinator folds

j385 (2026-10-24): `tools/fabric/python_pin.py` builds into `<prefix>/python-<ver>+<rel>~<16 hex>`, one `os.replace` of the link is the only mover, `_sweep` removes same-pin siblings after `check()` passes; the flat pre-change dir stays a build of its pin (`builds_of`). Tests (branch `for/user/j385-`, 14a8234b): a child `os._exit`s before each rename/replace/symlink/makedirs/rmtree call. A raised KeyboardInterrupt cannot show the SIGKILL window because the old handler caught it.

**Why:** a raise is caught by BaseException handlers; only an uncatchable exit proves the SIGKILL case.
**How to apply:** for a crash-safety test, kill the child with os._exit at step N and assert the invariant after each N; plant the old form and name the N it fails at (7 here). A file outside my entry goes as a patch in the REPLY body; `git restore` it afterwards so `fabric-jobs switch` finds a clean worktree. A wrapper `until grep '^exit '` matched the suite's own "exit codes" heading: use a unique marker.

*Anchors: `tools/fabric/python_pin.py::_sweep`, `tests/test_python_pin.py::kill_matrix`*

*Observed 2026-10-24 (python-dev)*
