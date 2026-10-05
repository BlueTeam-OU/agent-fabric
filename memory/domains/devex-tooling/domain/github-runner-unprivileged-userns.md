---
role: "devex-tooling"
class: domain
topic: "github-runner-unprivileged-userns"
description: "ubuntu-latest (24.04) blocks `unshare -r` via AppArmor; one sysctl lifts it, and a dummy link inside the netns needs no modprobe — measured 2026-09-25"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ffeaf60f8e7ae07b
---

## ubuntu-latest (24.04) blocks `unshare -r` via AppArmor; one sysctl lifts it, and a dummy link inside the netns needs no modprobe — measured 2026-09-25

On GitHub's hosted ubuntu-latest (24.04, kernel 6.17.0-azure, measured
2026-09-25 for InterWeave's mdns_bounds tests, commit 86faa715 there):

- `kernel.apparmor_restrict_unprivileged_userns` is 1, and `unshare -rn`
  fails with "write failed /proc/self/uid_map: Operation not permitted".
- `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` is the
  whole fix; no AppArmor profile change is needed.
- `ip link add X type dummy` inside `unshare -rn` works WITHOUT
  `modprobe dummy`, although lsmod does not list it. My assumption that
  module autoload is refused from a user namespace was wrong there.

**How to apply:** to verify a CI change on a runner before any PR exists,
push a throwaway branch carrying a workflow with
`on: push: branches: [<that branch>]` (push events use the workflow file
at the pushed commit), print the before-state as a control, then delete
the branch. Two such runs cost about 5 minutes.

Related: [[a-passing-run-without-the-trigger-measures-nothing]].

*References: a-passing-run-without-the-trigger-measures-nothing*

*Observed 2026-09-25 (devex-tooling)*
