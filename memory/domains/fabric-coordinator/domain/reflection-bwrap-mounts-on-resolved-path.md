---
role: "fabric-coordinator"
class: domain
topic: "reflection-bwrap-mounts-on-resolved-path"
description: "A bwrap sandbox spec (bind, mask, link) is decided on os.path.realpath against the bound roots and tested on both distro layouts through fixture root seams; deciding by the last component flipped fail-closed to fail-open on #358"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8abc7732401d978f
---

## A bwrap sandbox spec (bind, mask, link) is decided on os.path.realpath against the bound roots and tested on both distro layouts through fixture root seams; deciding by the last component flipped fail-closed to fail-open on #358

Six review rounds of a bubblewrap read-only sandbox each found a new hole in mount decisions:
- A whole-tree bind leaked what it held: config.worktree under the git dir, and `/etc/ssl/private` keys readable to members of a host group, because a bind keeps host modes and the caller's groups.
- An `isdir` test follows links. On Debian and Ubuntu `/usr/lib/ssl/private` is a link to `/etc/ssl/private`, so a `--tmpfs` landed on a dangling link and bwrap refused to start ("Can't mount on symlink destination").
- An `islink` test on the last component missed two cases. A link whose target sits inside a bound root got no mask and exposed the key: fail-closed had become fail-open. A link in a middle component made bwrap fail with "Can't mkdir parents".
- When a mask moved to the resolved path, the link the sandbox recreates had to move with it.

The rule that held: compute r = realpath(p). If r is absent, not a directory, or outside every bound root, apply no mask. If r is inside a bound root, mask r, never p. If r is a bound root or holds one, refuse to run. Bind an allowlist of named files, never a tree with denied parts. The dev host is Fedora and only CI's debian container has the other layout, so tests stand in a fixture /usr or /etc (a `usr=`/`etc=` seam) to exercise both layouts locally.

**Why:** every narrowing fix decided on the path as written opened the next hole, at one review round per hole.
**How to apply:** a REQUEST or review brief for a sandbox states the realpath rule and the allowlist up front, and asks for a fixture case per distro layout plus a real bwrap run. Assertions check bind verbs only, never substrings of argv: a mask is not a bind (#358's CI debian red).

*Observed 2026-10-25 (fabric-coordinator)*
