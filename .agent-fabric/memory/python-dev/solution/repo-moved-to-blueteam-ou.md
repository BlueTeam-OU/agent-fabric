---
role: "python-dev"
class: solution
topic: "repo-moved-to-blueteam-ou"
description: "from 2026-10-09 agent-fabric answers as BlueTeam-OU/agent-fabric; API writes through gzapi-org/ fail with HTTP 307 until the clone's origin is updated by the next fabric upgrade"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1f99e9ab3ddb0644
---

## from 2026-10-09 agent-fabric answers as BlueTeam-OU/agent-fabric; API writes through gzapi-org/ fail with HTTP 307 until the clone's origin is updated by the next fabric upgrade

The owner moved agent-fabric (with agent-fabric-gateway, agent-fabric-herdr, radicle-spike) from gzapi-org to BlueTeam-OU on 2026-10-09. Reads and git push follow the redirect; `fabric-pr post-review`, `reply` and `arm` POST through the old name and fail with HTTP 307. Until a fabric upgrade rewrites origin: run those with `GH_REPO=BlueTeam-OU/agent-fabric` in front (an exported variable does not survive between Bash calls). gzapp and the other repos did not move. The coordinator's broadcast was 01a12152-aa55 (after python-dev-03's observation 01a12152-3dca).
**Why:** found when a review post was rejected; gh's own `--repo` redirect handling does not cover POST.
**How to apply:** any gh write against agent-fabric before the upgrade; drop the prefix once `git remote -v` names BlueTeam-OU.

*Observed 2026-10-09 (python-dev)*
