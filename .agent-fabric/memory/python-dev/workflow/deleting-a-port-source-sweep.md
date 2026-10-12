---
role: "python-dev"
class: workflow
topic: "deleting-a-port-source-sweep"
description: "Deleting the old implementation of a port (Wave 8 s8, #170): what breaks that a grep of paths does not find, and how the frozen oracle replaces the differential test"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8a0fdceba9982b04
---

## Deleting the old implementation of a port (Wave 8 s8, #170): what breaks that a grep of paths does not find, and how the frozen oracle replaces the differential test

Deleting the Node control plane (#170) left four failures only the full `tests/run.sh python` run with CI's environment found: a test that read the deleted file's constant (`usage.mjs` PROBE_MODEL), a second fixture that lints a tree (test_assemble) after a lint rule began to require a file, a new test missing `own_instance_tree()` (tests/test_own_instance_tree.py scans for it), and a coordinator-supplied `commands.json` change that emptied `replaces`. Run the full python section before opening the PR, not only the files you edited; and a path grep for `.mjs` misses bare names (`usage.mjs`), constants read by regex, and fixtures.

The differential tests (Node beside Python) become frozen answers: run the old harness once from a worktree of origin/main, store the Node answer next to the case's input and Python body (tests/fixtures/node-oracle-*.json), never sort keys (answer order follows input order), and name each post-deletion addition in the test and strip exactly that text before comparing. A blind review will mutate single lines and find the cases you did not freeze (ctl tables, upgrade check_args): plant those mutants yourself first.

**Why:** the review of #170 found 4 surviving mutants and 3 red suites after the first push. **How to apply:** before the first push of any deletion PR: full python section, mutants on each behaviour the deleted tests compared, and list the coordinator-owned hunks (bootstrap, lint, run.sh, commands.json, arm.json, mcp) as patches posted on the PR.

*Observed 2026-10-10 (python-dev)*
