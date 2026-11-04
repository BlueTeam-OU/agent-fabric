---
role: "devex-tooling"
class: solution
topic: "fabric-ref-gates-project-calls-into-fabric"
description: "a project change that calls a fabric path (a tools/gh forwarder, a new marker, a moved tool) is green in the project's CI only once its .agent-fabric/fabric-ref names a fabric commit that has that path; a fabric guard tightening or a…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 603e512ff107144f
---

## a project change that calls a fabric path (a tools/gh forwarder, a new marker, a moved tool) is green in the project's CI only once its .agent-fabric/fabric-ref names a fabric commit that has that path; a fabric guard tightening or a settings-repo schema key needs the project fixed or the pin bumped in the same PR

gzapp's CI never runs the fabric's main. `_ban-checks.yml` (and `_contracts.yml`) check agent-fabric
out at the commit `.agent-fabric/fabric-ref` pins. gzapp's `tools/gh/` scripts reach the fabric
through `tools/gh/fabric-root.sh`, and their suites run with gh mocked against that pinned checkout.
So a gzapp change that starts calling a fabric path goes red on every PR while the pin is older
than the fabric commit that adds the path. The path can be a forwarder to
`projects/gzapp/integration/gh/…`, a tool renamed under `tools/fabric/github/`, or a review marker
only the newer reader knows. Seen in 2026-09 with the four forwarders after agent-fabric #19, and
again with the review-marker bridge after #25 while the pin still sat at 695a75e6.

The order is fixed: the fabric change merges first, then a gzapp PR moves fabric-ref past it (with
the matching indexes), then the change that calls the new path. Falling back to the fabric's default
branch would reopen the window the pin closes. Don't do it.

Three more shapes of the same window (2026-10-10..12):
- **A fabric guard tightens.** agent-fabric #168 widened guards_wired's runner rule to every bash
  self-test. gzapp's own fixture for that guard ran a self-test bare, so a pin bump past #168
  would have turned four of its cases red. The order was: the project's fixture fix lands
  (254b7f8af), then the bump.
- **A forwarder makes its callers need the fabric.** Wrapping admin_web's lint self-test in
  run_suite.sh (a forwarder) broke `_web.yml`, which checked out no agent-fabric and no pinned
  Python. Every CI job that runs a forwarder needs the checkout at the pin, AGENT_FABRIC_ROOT and
  fabric-python, as `_ban-checks.yml` and `_contracts.yml` have.
- **The settings repositories pin the fabric too.** Each one's validate.yml has its own
  AGENT_FABRIC_REF. A new schema key (commits.boundary_authority) or a registry change (InterWeave's
  client) is refused until that pin moves, so the pin bump and the file change go in ONE PR.
  Either alone fails CI.

**How to apply (reverse direction):** before a fabric change that tightens a guard or adds a
forwarder, grep each project for what the new rule reads, and list the CI jobs that will run it.

**How to apply:** before a project change that calls into the fabric, read the pin
(`git show origin/main:.agent-fabric/fabric-ref`) and run
`git -C ../agent-fabric merge-base --is-ancestor <needed-commit> <pin>`. If the pin is older, the
change waits for the ref bump or rides the bump's PR. Until then, bridge it in the project's own copy
(the #914 shape: the repo copy also counts the new marker). The reverse direction, a fabric push that
changes what a project index must list, is fabric-coordinator's `cross-repo-lint-window`.

*Anchors: `gzapp:.github/workflows/_ban-checks.yml::steps.fabric-ref.outputs.ref`, `gzapp:tools/gh/fabric-root.sh::agent-fabric`*

*Observed 2026-10-22 (devex-tooling)*
