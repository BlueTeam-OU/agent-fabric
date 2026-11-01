---
role: "legal-expert"
class: workflow
topic: "inbox-exit-6-rearm"
description: "gzcoord-inbox exit 6 \"schema version N, newer than this code's M\" after a fabric upgrade — re-arm once; no checkout fast-forward job needed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f6acf1a02c1bd0ec
---

## gzcoord-inbox exit 6 "schema version N, newer than this code's M" after a fabric upgrade — re-arm once; no checkout fast-forward job needed

On 2026-10-30 my watch exited 6 (episodic.db schema 3, code 2) and I queued j15 to fast-forward the agent-fabric checkout. The fabric-coordinator broadcast (01a18c45-983c-7caa-8aed-9bdf8929d40f, fabric d941d5b0, #425) said the cause: a watch armed before the upgrade still has the old journal code loaded. When the fresh session started, the checkout was already at origin/main and a new watch ran fine. The held message came again, because it had not been acknowledged.

**Why:** distribution updates the account's checkout. Only the running process is stale.

**How to apply:** if the watch exits 6 naming a newer schema, check `git rev-parse HEAD origin/main` first. If they match, just arm the watch again; don't open a job for it. See [[inbox-watch-only-via-harness]].

*References: inbox-watch-only-via-harness*

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::--until-delivery`*

*Observed 2026-10-30 (legal-expert)*
