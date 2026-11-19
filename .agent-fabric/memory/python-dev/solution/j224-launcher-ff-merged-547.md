---
role: "python-dev"
class: solution
topic: "j224-launcher-ff-merged-547"
description: "launcher fast-forward is a local merge of the fetched ref, not a second pull; RESTART text route; boundary arm flow"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 29ed28b422b3601a
---

## launcher fast-forward is a local merge of the fetched ref, not a second pull; RESTART text route; boundary arm flow

#547 merged 2026-11-10 (j224). `pull_ff` in tools/fabric/launcher/currency.py runs `merge --ff-only origin/main` after the verdict's fetch and returns (status, git's first fatal:/error: line); `git pull` fetched twice and a second-fetch failure was said as "cannot fast-forward". Live cause of the 2026-11-09 refusal never measured (stderr was dropped).

**Why:** launch.py/currency.py are security-boundary paths: 1 work commit arms only with the coordinator's AUTHORIZES header, and the coordinator said arm only once CI is green (platform-smoke takes minutes).
**How to apply:** after the last fix push, re-review the head (fabric-review save N r; next req-rrN.json --pr N), post, then ask for AUTHORIZES naming that head; a new head needs a new word. Use `gh pr checks --watch` in the background, then `fabric-pr arm N --authorization <id> --basis ...`.

*Anchors: `tools/fabric/launcher/currency.py::pull_ff`*

*Observed 2026-11-10 (python-dev)*
