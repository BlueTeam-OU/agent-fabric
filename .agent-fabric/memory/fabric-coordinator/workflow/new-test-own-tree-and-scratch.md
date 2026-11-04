---
role: "fabric-coordinator"
class: workflow
topic: "new-test-own-tree-and-scratch"
description: "A brief for a new tests/test_*.py must say: call own_instance_tree() before any definition if it hands a tool a tree, and remove its mkdtemp scratch at exit; the full suite fails both, and a single-file run catches neither"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8ab3d288f0aca146
---

## A brief for a new tests/test_*.py must say: call own_instance_tree() before any definition if it hands a tool a tree, and remove its mkdtemp scratch at exit; the full suite fails both, and a single-file run catches neither

2026-10-19, #323: two CLI oracles a subagent wrote for Wave 9 batch 2 passed alone and were red in
CI's full run on two counts: tests/test_own_instance_tree.py ("starts without the runner's
operator": a test that hands a tool a tree via AGENT_FABRIC_ROOT, --fabric, --root or EXTRA calls
`own_instance_tree()` from instance_fixtures before any definition), and the runner's
"scratch left behind" check (their `tempfile.mkdtemp` dirs outlived them). Fixed in 23798b69 with
the import and `atexit.register(shutil.rmtree, tmp, ignore_errors=True)`.

**Why:** both conventions are enforced only by the full run, so a subagent told to run "the new
test and lint" never sees them.

**How to apply:** every brief that adds a tests/ file names both rules, and the collection step
runs tests/test_own_instance_tree.py and the new file under a fresh TMPDIR, counting leftovers.
Related: [[find-oracle-by-docstring]], [[fold-then-full-suite]].

*References: find-oracle-by-docstring, fold-then-full-suite*

*Anchors: `tests/test_own_instance_tree.py::starts without the runner's operator`, `tests/instance_fixtures.py::own_instance_tree`*

*Observed 2026-10-19 (fabric-coordinator)*
