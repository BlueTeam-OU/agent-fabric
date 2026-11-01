---
role: "python-dev"
class: solution
topic: "launcher-link-follows-moved-mask"
description: "sandbox launcher --symlink must be made at the mask's resolved place (masked[p] + rest), not at the name; real-bwrap proof pattern for a fixture /usr"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e93323409e1b3ba6
---

## sandbox launcher --symlink must be made at the mask's resolved place (masked[p] + rest), not at the name; real-bwrap proof pattern for a fixture /usr

#358 round 6 C1 (j159): when `/usr/local` is a link into `/usr`, `mask_target` puts the tmpfs on the resolved dir, so the launcher link
(`python_pin.LINK`) must be made at `masked[p] + LINK[len(p):]` with `os.readlink(host_of(LINK, usr))` as text (`sandbox.py`). Test counts only
links ending `fabric-python` (the argv also carries the fixed system links), and runs bwrap for real with the fixture bound at /mnt plus a
no-link control. Mutation `masked.get(path) == path` fails the moved cases.

**Why:** a link made at the name is made through the link, under the tmpfs.
**How to apply:** delivery went as a diff in a REPLY because the job-copy guard blocks commits in a for/ worktree (j158 fixes that). See [[mask-on-the-resolved-path]].

*References: mask-on-the-resolved-path*

*Observed 2026-10-24 (python-dev)*
