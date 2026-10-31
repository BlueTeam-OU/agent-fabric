---
role: "python-dev"
class: solution
topic: "j62-launch-locale-holder-fallback-merged"
description: "#302 merged — launch_locale.read falls back to launch-holder.json; dangling-symlink rule, doc outside entry"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 121525888a824197
---

## #302 merged — launch_locale.read falls back to launch-holder.json; dangling-symlink rule, doc outside entry

#302 (1 work, 1 fix) merged 2026-10-18. `launch_locale.read`: launch-locale.json present (lexists, dangling included) decides alone; absent -> launch-holder.json `holder.locale`; `holder: null` is silent en; unusable is stderr + en.

**Why:** sessions launched before 1e64ebd9 have only launch-holder.json; the installer removed their locale-worker.
**How to apply:** `install_agent_files.py` docstring (lines 24-26) is outside python-dev's entry; I sent fabric-coordinator an INFO to add the fallback. A `git add -A` before a refused commit stages files outside the entry: `git restore --source=HEAD --staged --worktree <file>`. Re-review brief needs `card_base` and `previous_findings` file; objective must state what must be true.

*Observed 2026-10-18 (python-dev)*
