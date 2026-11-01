---
role: "python-dev"
class: solution
topic: "mask-on-the-resolved-path"
description: bwrap tmpfs masks must be decided on realpath, not the name; roots bound after the masks are not consulted; fixture usr stands for /usr
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f4db0adde56cfac8
---

## bwrap tmpfs masks must be decided on realpath, not the name; roots bound after the masks are not consulted; fixture usr stands for /usr

review_mcp/sandbox.py mask_target(path, roots) (#358 round 5, j157, b55acf31): realpath r; absent/non-dir or outside the system roots (/usr, plain SYSTEM_LINKED dirs) -> no mask; inside -> --tmpfs on r as it shows inside; r equal to or holding a root -> Unproved. Debian's /usr/lib/ssl/private -> /etc/ssl/private dangles inside, so no mask there.

**Why:** a last-component islink check let a link into the bound /usr go unmasked (fail-open) and a middle-component link got a tmpfs bwrap refuses. Counting roots bound after the masks (toolchain under /usr/local) would refuse every host.
**How to apply:** any new mask goes through mask_target; a real-bwrap test can stand a fixture at /mnt via roots=[(realpath(fixture), "/mnt")] with `--ro-bind / /`, since the host /usr cannot be edited. An amend with no path is refused here: reset --soft and recommit.

*Observed 2026-10-24 (python-dev)*
