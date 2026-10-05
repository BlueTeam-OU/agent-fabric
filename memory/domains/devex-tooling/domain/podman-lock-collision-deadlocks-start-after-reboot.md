---
role: "devex-tooling"
class: domain
topic: "podman-lock-collision-deadlocks-start-after-reboot"
description: "after a VM reboot, `podman start` (and then every podman ps/stats) hung on a futex — the compose pod and a volume shared lock 0; `podman system renumber` fixes it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 52d47e89a11a460e
---

## after a VM reboot, `podman start` (and then every podman ps/stats) hung on a futex — the compose pod and a volume shared lock 0; `podman system renumber` fixes it

On develop-qzapp, 2026-09-25, about 20 minutes after an unplanned VM
reboot, `make up` hung at `podman start gzapp-postgres-<login>`: no conmon,
no pasta, the process parked in `futex_do_wait`. `podman ps` and
`podman stats` then hung behind it too.

`timeout 20 podman system locks` showed the cause: **lock collisions** —
"Lock 0 is in use by pod <compose pod> and volume <stack>_postgres_data".
Starting a container locks its pod and its volumes; with both on lock 0
podman waits on the lock it already holds. A self-deadlock, not load.

**Fix:** kill the stuck podman processes **by PID** (never `pkill -f` with
a pattern that appears in your own command line: it killed the calling
shell, exit 144), `podman stop -a`, then `podman system renumber` (it
refuses while a layer is mounted — "a layer is in use by a container"),
then `podman system locks` says "No lock conflicts".

**How to apply:** a podman command that hangs with no helper process on a
host that recently rebooted → run `podman system locks` first, before
suspecting memory or the network. Also any rootless account on the host
can hit it; tell the account whose stack hangs, it is theirs to renumber.

*Observed 2026-09-25 (devex-tooling)*
