---
role: "fabric-coordinator"
class: threads
topic: "threads-2026-10-13-shutdown"
description: "Open threads when the owner shut the fleet down on 2026-10-13 ~17:10: #238 to arm, #239, settings-put on #236, avatars, store remotes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1358afc53095add
---

## Open threads when the owner shut the fleet down on 2026-10-13 ~17:10: #238 to arm, #239, settings-put on #236, avatars, store remotes

At the 2026-10-13 shutdown (sessions SIGTERMed, deck/herdr and 25 control agents stopped, per
[[fleet-shutdown-procedure]]):

- **#238 MERGED 2026-10-13 19:3x as bbbc14d8, fleet upgraded.** Was: (branch develop-qzapp/user/adr-056/accepted, worktree in my scratchpad): ADR-056 accepted
  + amended (avatar folder), 26 claims, avatar-style.md, persona-profile schema, ADR-057 accepted +
  ADR-038 amended. Round 3 clean on claude and codex, both posted on head 18cdf593. Gate 9 work /
  2 fix; CI checks were still running. Next: checks green → `fabric-pr arm 238` (≥8 work, gate met),
  wait-merged, `fabric-ctl all upgrade fabric`.
- **#239** python-dev-03's fabric-sign (red until #238 merges). Mine after: policies/signing.json
  (per-repo `since`), the checker in tools/fabric/guards, bootstrap git settings (gpg.program,
  gpg.ssh.program, gpg.format, user.signingkey; never notes.rewriteRef), CI fetching refs/notes/fabric-ots.
- **#236** python-dev-02: adding `fabric-secrets store settings-put --from <dir>` (one signed commit
  per persona); then announce to all agents, who hold accepted avatars in their scratchpads. Agents
  must not hand-clone their store (auto mode refuses, rightly). Some (brand-comms-01 21f92fe,
  python-dev-01, maybe 5 "delivered") pushed by hand: python-dev-02 checks verify-on-pull.
- **Avatars** in /usr/local/share/agent-fabric/avatars/<id>/ (brand-comms-01 owns, 0755); sheet.png;
  language-culture-ru asked for a redraw. Mine: AI Rowan Babbage, M.
- **Owner pending:** store remotes `! /run/user/1000/store-remotes/fix.sh --apply` (all 26 still on
  gzapi-org via redirect; /run is lost at reboot: rewrite the script then); Tereza/Vera duplicate
  first names; arm #236.
- arm false-failure fix requested of devex-tooling (REQUEST 01a13565, job j115).

- After the evening reboot: fleet up by hand (agent link fix, see [[fleet-boot-agent-link]]); one-command boot = rust-ui-dev-02 j11 (fleet-deck --auto) + python-dev-04 #240 (fabric-ctl control-start/stop, owner arms: 1 work). /run was wiped: the store-remote script must be rebuilt.

*References: fleet-boot-agent-link, fleet-shutdown-procedure*

*Observed 2026-10-13 (fabric-coordinator)*
