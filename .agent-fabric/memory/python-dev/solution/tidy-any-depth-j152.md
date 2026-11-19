---
role: "python-dev"
class: solution
topic: "tidy-any-depth-j152"
description: "j152 #628 — find_targets MAX_DEPTH=4 was shared by switch and tidy; tidy now unlimited, prunes other filesystems; review/arming/tool traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5ff12d432167958b
---

## j152 #628 — find_targets MAX_DEPTH=4 was shared by switch and tidy; tidy now unlimited, prunes other filesystems; review/arming/tool traps

`leave_targets.find_targets(max_depth=MAX_DEPTH)`: switch keeps 4 levels, tidy and held_output pass `max_depth=None`. With no depth limit the walk must not cross a mount: `same_device` prunes a dir whose `st_dev` differs and appends it to `mounts` (tidy and switch print `kept <dir>: another filesystem, not entered`); unlistable dirs go to `errors` (tidy_tree now warns). Test fakes a mount by wrapping `os.lstat` (same object as `lt.os.lstat`); held sizes count 4 KB blocks per small file.

**Why:** a hygiene round left spikes/…/node/target (5 deep); review rounds found the mount crossing (F1) and silent pruning (F3) as consequences of lifting the limit.

**How to apply:** lifting a walk limit needs the xdev rule and a said line for everything not entered. Traps: `git checkout <file>` after a sed-mutation also reverts the real edit (use a copy); `fabric-pr post-review` must be the bare command with `--repo`, report from a file; `fabric-review next --pr` needs `fabric-review save PR ROUND` first and prints the brief to stdout (give the re-review agent the file path); `fabric-jobs deliver` takes `owner/repo#N`, not `pr:N`; below-minimum arming only for urgent work, owner rides further jobs onto the open PR.

*Anchors: `tools/fabric/jobsparts/leave_targets.py::same_device`, `tools/fabric/jobsparts/tidy.py::tidy_tree`*

*Observed 2026-11-16 (python-dev)*
