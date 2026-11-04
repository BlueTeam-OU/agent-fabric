---
role: "edge-hosting"
class: workflow
topic: "inbox-watch-only-via-background-tool"
description: "Start gzcoord-inbox only as the harness's background command, never with & or disown inside another command"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b9bbdd7f2968b884
---

## Start gzcoord-inbox only as the harness's background command, never with & or disown inside another command

Start `gzcoord-inbox --until-delivery` only as its own Bash call with run_in_background. Never append it to another command with `&` or `disown`.

**Why:** on 2026-10-27 I tacked `gzcoord-inbox --until-delivery >/dev/null 2>&1 & disown` onto a disk-measure command. The result was an orphan watch whose output went to /dev/null. A delivery it took would be lost unseen. The hooks refuse to kill an inbox watch, and `--replace` refused it because a detached watch is "not provably a watch of this session". So it could only run out its 115 minutes.

**How to apply:** if it happens again, don't try to kill or replace the orphan. Wait for its pid to exit. Then re-arm properly and check `gzcoord-inbox --replay` for anything delivered while it ran. Related: [[home-disk-footprint]].

*References: home-disk-footprint*

*Anchors: `tools/fabric/gzcoord/inbox_parts/watchlock.py::replaceable_of`*

*Observed 2026-10-27 (edge-hosting)*
