---
role: "devex-tooling"
class: solution
topic: "brand-comms-arming-grant"
description: "where the brand-comms \"arm without asking\" grant lives (two settings repos), what it covers and what is still pending"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a2a82592cba704bc
---

## where the brand-comms "arm without asking" grant lives (two settings repos), what it covers and what is still pending

The owner's grant of 2026-10-19 lets brand-comms arm its own PRs in blueteam.brand, blueteam.ee, gzapi.brand, gzapi.ge and gzapp.decks. It is `commits.roles.brand-comms.min = 1` in repos/<repo>.json of BlueTeam-OU/agent-fabric-settings (#8, merged 189d387d) and gzapi-org/agent-fabric-settings (#7, merged 08dc4cfe). blueteam.brand went from owner-only to direct in the same change.

To check it live, use `arm_policy.load(repo)` and then `threshold(policy, role, cls, boundary)`. That reads the settings repository's default branch, as arm itself does. The expected answer is brand-comms 1, boundary 8, other roles 8.

The boundary was narrowed, not removed (the owner, via fabric-coordinator's REPLY 01a152c7-0119, 2026-10-19): agent-fabric #310 (merged 7715fe6d, 2026-10-19) keeps .claude/, .mcp.json, .github/, .env*, .npmrc, package manifests, pnpm files, deploy scripts and secret files in each projects/<id>/integration/gh/arm.json, and drops content (src/, public/, brand/, theme/, scripts/, astro, tsconfig). After #310, a brand-comms content PR arms at 1 work commit; a PR touching the narrowed boundary still needs 8 or a second word. See [[role-minimum-typed-trailer]] for the trailer caveat.

Verified live 2026-10-19 after #310 merged: all five repos read brand-comms 1, other roles 8, boundary 8. j156 delivered on that.

*References: role-minimum-typed-trailer*

*Anchors: `tools/fabric/github/arm_policy.py::def threshold`*

*Observed 2026-11-01 (devex-tooling)*
