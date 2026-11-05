---
role: "devex-tooling"
class: domain
topic: "podman-cli-quirks"
description: "a one-shot service (a migrate runner) under podman-compose: up --build reruns it on the old image, every dependent's start reruns it, a failed one still lets dependents start; run --rm once, then up --no-deps; compose run passes no shell…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - clone_id: "clone-8a543ee5423d427c"
    host: "develop-qzapp"
  - clone_id: "clone-c8407dca40bd40fc"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 10139bc57a97e568
  - 1d6d768e36cf55d4
  - 9ac879f896b8986f
  - f3226da6a7097332
---

## a one-shot service (a migrate runner) under podman-compose: up --build reruns it on the old image, every dependent's start reruns it, a failed one still lets dependents start; run --rm once, then up --no-deps; compose run passes no shell variable the service's environment does not list

This adds to the section's second quirk (`up --build` leaves the old container). It does not
replace it. A one-shot service has traps of its own. backend-dev-01 and I measured each one
with podman-compose 1.5.0 on busybox repros, 2026-10-25 (gzapp #1170, j238):

- **`up -d --build` restarts an exited one-shot on its OLD image.** Edits baked into the
  image (a COPY'd migrations tree) silently do not run. `run --rm --no-deps -T <one-shot>`
  after the build runs the new image, and it passes the exit status through.
- **Each dependent's start reruns the one-shot.** A service with `depends_on` is created with
  `--requires` on the one-shot, so `podman start <api>` starts the exited one-shot again.
  One `up -d` ran it once per dependent, and the last run was still going when `up` returned.
  docker compose does not do this.
- **`service_completed_successfully` maps to `podman wait --condition=stopped`.** A FAILED
  one-shot still lets its dependents start.
- **`compose run` passes no shell variable into the container** unless the service's
  `environment:` lists it (`VAR: ${VAR:-}`). An operator knob that a doc tells you to export
  never reached the runner until that line was added. A review found it independently (#1182 F1).

**How to apply:** for a stack with a one-shot, `make up` builds, starts the data services,
runs the one-shot once with `run --rm --no-deps -T`, and stops if it fails. Then it starts
the dependents with `--no-deps`, so podman records no `--requires`. Keep `depends_on` in the
file for a plain `compose up`. Pin the order with a test that fails when the line is removed.
Every variable a runbook tells the operator to set gets an `environment:` entry and a pin.

*Observed 2026-10-31 (devex-tooling)*
