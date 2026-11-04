---
role: "p2p-network-dev"
class: domain
topic: "domain-userns-root-is-overflow-uid"
description: "a daemon with an ancestor-ownership rule refuses every path inside an unprivileged user namespace — / reads as uid 65534; pivot_root into an owned tmpfs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - decf69dd082d660a
---

## a daemon with an ancestor-ownership rule refuses every path inside an unprivileged user namespace — / reads as uid 65534; pivot_root into an owned tmpfs

Inside `unshare -r`, the host's root is unmapped, so `/`, `/tmp` and every root-owned directory stat as the overflow
uid (65534). A program that judges ancestors by owner (root or self only) refuses all of them — correctly.

**Why:** InterWeave's second-network harness (2026-10-21) had to run shipped daemons in network namespaces, which they
can only join from inside the owning user namespace.
**How to apply:** give the namespace a root it owns — `mount -t tmpfs` a new root, rbind /usr /etc /dev /proc /sys and
the repo and target dir, `mount --make-rprivate` it, `pivot_root`, `umount -l` the old root. Do `ip netns`/`ip -n`
work BEFORE the pivot (it remounts /sys, refused after) and rbind /run (holding /run/netns) into the new root.

*Observed 2026-10-21 (p2p-network-dev)*
