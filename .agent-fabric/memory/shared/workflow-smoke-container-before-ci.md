---
role: shared
class: workflow
topic: "smoke-container-before-ci"
description: "Run a platform smoke job under podman on this host, as an unprivileged login, before pushing a CI change that adds a container job — the containers find host facts (a missing cmp, Debian's /etc/profile resetting PATH, dash as sh) that the…"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8426a37c6be555fe
---

## Run a platform smoke job under podman on this host, as an unprivileged login, before pushing a CI change that adds a container job — the containers find host facts (a missing cmp, Debian's /etc/profile resetting PATH, dash as sh) that the ubuntu runners never do

Before pushing a CI change that adds or edits a container job, run the
same sequence under `podman run --rm -v "$PWD:/src:ro,z" <image>` on
this host, copying the tree to `/work`, installing from
`runtime/provisioning/platform/packages.sh <platform>`, and running the
suites as a fresh unprivileged login (`useradd -m ci && su ci -c …`),
never as root. Use `:z` (shared label), not `:Z`, when two containers
mount the same source — the second private relabel locks the first out.

**Why:** on 2026-09-16 the first push of the Fedora/Debian smoke jobs
failed four ways the ubuntu matrix could not show: a Fedora container has
no `cmp` (bootstrap's idempotence rewrote every file), Debian's
`/etc/profile` assigns PATH outright for a non-root login shell (an
as-login command lost the worker's PATH and downloaded the real claude in
place of the test's fake), a container's default step shell is dash on
Debian (`Bad substitution` sourcing a bash profile), and the runner's
login is root, which `new-agent.sh` refuses. Each cost a CI round trip
that a local podman run found in minutes. Commits `cf14d55`, `f7fc062`
in agent-fabric.

**How to apply:** treat the podman run as the read-back a `docs/live-
checks/` entry asks for; the CI job is the fence, not the first run.

*Observed 2026-09-16 (fabric-coordinator)*
