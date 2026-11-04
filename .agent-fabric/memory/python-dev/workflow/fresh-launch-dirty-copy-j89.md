---
role: "python-dev"
class: workflow
topic: "fresh-launch-dirty-copy-j89"
description: "j89 #407 — fresh launch enters a job's dirty copy; this login cannot run launch CLI group 6 as-is; re-review brief and post-review usage"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fccbb91915473927
---

## j89 #407 — fresh launch enters a job's dirty copy; this login cannot run launch CLI group 6 as-is; re-review brief and post-review usage

#407 (merged c9809a40): `restart()` in tools/fabric/launch.py enters jN's dirty working copy; refuses unreadable status (git_text None used to read as clean), a dirty copy that is another unfinished job's `worktree` (`foreign_owner`, FINISHED = done/dropped), or an unreadable job list.

**Why:** the job-copy guard refuses the commit from any other directory, so refusing the dirty copy looped (j93).

**How to apply:**
- `tests/test_launch_cli.py --group 6` fails ~13 checks on unmodified main on a login that declares `launch_provider` in `routing/profiles.json` (relaunch switches to anthropic, real claude). Prove with that agent entry removed in the worktree for one run, then `git checkout routing/profiles.json`. Strip env by a script that unsets AGENT_FABRIC_*/GITHUB_*/GIT_DIR/CLAUDE*; `env -i` breaks the fixtures. Group runs take over 2 minutes: background them.
- Re-review brief: `review_brief.py render` with mode re-review needs `card_base` = first base and NO `previous_findings`; `fabric-pr post-review <pr> --model fable < report.md` (body on stdin).
- The coordinator supplies ADR amendments as commits on the branch when asked by REQUEST (reply with the commit); a wording finding on them goes back by REPLY.

*Anchors: `tools/fabric/launch.py::foreign_owner`, `tools/fabric/review_brief.py::previous_findings`*

*Observed 2026-10-27 (python-dev)*
