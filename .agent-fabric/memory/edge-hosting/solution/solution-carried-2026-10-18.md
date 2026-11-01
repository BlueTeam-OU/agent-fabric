---
role: "edge-hosting"
class: solution
topic: "solution-carried-2026-10-18"
description: "blueteam.ee unreachable from develop-qzapp but up elsewhere — 1984 Hosting firewall dropping our one egress IP"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6a4f4ec26c0bea30
  - db1c1e3f614d4215
---

## blueteam.ee unreachable from develop-qzapp but up elsewhere — 1984 Hosting firewall dropping our one egress IP

blueteam.ee is served from 185.112.145.204 (1984 Hosting, AS44925; NS ns0/1/2.1984.is, ns1/2.1984hosting.com; MX Proton). develop-qzapp's egress is 213.200.31.205 (Magticom fixed line, AS16010), shared by every agent on the host.

On 2026-10-15 (about 11:00–11:45Z) every port on .204 timed out from develop-qzapp while check-host.net nodes got 200, Magti mobile reached it, and the same-/24 neighbour 185.112.145.81 (1984hosting.com) answered us. Cause, per 1984 support relayed by the owner: a glitch in their firewall; they also whitelisted 213.200.31.205. Their first answer ("not blacklisted") did not fix it; the neighbour-answers evidence did.

**How to apply:** when the site is unreachable from here, compare an outside vantage (check-host.net API) and a same-/24 neighbour before calling it down; if only our address fails, it is the provider's per-host firewall — the owner asks 1984 support, and agents stop probing meanwhile.

The deploy target this concerns is in the blueteam.ee repository, not agent-fabric: `../blueteam.ee/deploy/target.json` (SFTP, port 2222; re-checked on origin/main bcd6b6f, 2026-10-20). It is cited as a sibling path and carries no anchor, because an anchor is only looked for in the slice's origin checkout, which is agent-fabric.

*Observed 2026-10-15 (edge-hosting)*
