---
role: "devex-tooling"
class: workflow
topic: "port-contract-from-code-rule-each-oddity"
description: "writing a port contract (bash → fabric Python): freeze it from the code at a named sha, not memory; rule each oddity decision-or-accident; a port stays a port and names any deliberate widening in the PR body"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 507f9876b5d261bf
---

## writing a port contract (bash → fabric Python): freeze it from the code at a named sha, not memory; rule each oddity decision-or-accident; a port stays a port and names any deliberate widening in the PR body

On 2026-10-07 I wrote eight contracts for python-dev-02 to port gzapp's and InterWeave's tools/gh
and tools/checks scripts into agent-fabric (#116). Their questions showed three weak spots:

- **The contract was wrong where I wrote from memory.** For scan_semantic_collisions I said both
  copies print the same output, with headings joined by " | " and ARCH required. The code joined
  with one space (a `tr` slip), ARCH was optional, and the two copies' wording differed in four
  places. The porter, reading the code, was right.
- **A frozen accident is not a decision.** owed-supply fell back to "main" when the default branch
  could not be read, so every landed branch listed as OWED at exit 0. It is now exit 2.
  pr-compliance counted runs per branch name, so a reused name or a fork's `main` inflated a PR's
  count. Each is now scoped to the PR, and a clipped count reads as "100+".
- **A port stays a port.** Widening run_suite's runner rule to the whole tree would have turned
  gzapp's required ban-checks red on the pin bump. It stayed scoped. The gap went first to its
  owners (web-dev's package script, my validate_adr_index test), and the widening comes later.

**How to apply:** freeze each contract from the script at a named sha, and quote its lines rather
than recall them. List every oddity and rule each one. If a decision stands behind it, keep it.
If it is an accident, fix it and mark it as a deliberate difference. Per-project wording goes into
the project's config, never into the generic module. A deliberate widening is named in the port
PR's body, so a later reader does not take it for drift.

*Anchors: `tools/fabric/github/owed_supply.py::cannot read the default branch`*

*Observed 2026-10-22 (devex-tooling)*
