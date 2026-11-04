---
role: "edge-hosting"
class: workflow
topic: "cite-other-repo-paths-as-siblings"
description: "In a memory about another repository, cite its paths as ../<repo>/path, and anchor them with the project prefix <id>:path::literal, never bare"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a4b7cb69132696b4
---

## In a memory about another repository, cite its paths as ../<repo>/path, and anchor them with the project prefix <id>:path::literal, never bare

My memory directory belongs to the agent-fabric project, so the drain gives every memory I write the origin agent-fabric. A bare path such as `deploy/target.json` or `.claude/skills/` is therefore checked against agent-fabric's tree. When the file actually lives in blueteam.ee or gzapp, the check reports it stale-hard. The memory check flagged two sections this way on 2026-10-20 (REQUEST 01a157ca, job j18).

**Why:** `tools/fabric/memory_check.py` resolves a `../NAME/rest` citation in the sibling checkout. A bare anchor is looked for only in the slice's origin checkout, so a bare anchor on another repository's file can never be found. Since 28be3753 (2026-10-20, j307), an anchor that names its project (`gzapp:apps/x/README.md::literal`, a projects/registry.json id) is judged in that project's checkout instead. This corrects my earlier rule here of "no anchor at all".

**How to apply:** write a path in another repository as `../blueteam.ee/deploy/target.json`, and anchor it as `<registry id>:<path>::<literal>` (for example `blueteam.ee:deploy/target.json::<key>`), never as a bare path. Related: [[solution-carried-2026-10-18]], [[rationale-carried-2026-10-18]].

*References: blueteam-host-single-ip-drop, site-deploy-tooling-lives-in-project*

*Anchors: `tools/fabric/memory_check.py::judge_anchor`*

*Observed 2026-10-20 (edge-hosting)*
