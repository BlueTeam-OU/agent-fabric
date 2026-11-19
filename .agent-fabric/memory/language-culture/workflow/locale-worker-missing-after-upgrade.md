---
role: "language-culture"
class: workflow
topic: "locale-worker-missing-after-upgrade"
description: "Agent type locale-worker not found: the installer took the locale as en without a launch record; --locale ge and relaunch"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 06ca5946fb872757
---

## Agent type locale-worker not found: the installer took the locale as en without a launch record; --locale ge and relaunch

On 2026-10-19 `locale-worker` was missing from the session: install_agent_files.py reads the locale from launch-locale.json (1e64ebd9), and without that file it resolves "en" and removes the worker. My launch predated the record. Fix: `install-agent-files.sh --locale ge` (tag `ge`, not `ka-GE`), then relaunch with `fabric-fresh --job <id>`, because the agent list is read at launch. Reported to fabric-coordinator (OBSERVATION 01a150b1-f4d7).

*References: locale-worker-needs-model*

*Observed 2026-11-09 (language-culture)*
