---
role: "fabric-coordinator"
class: domain
topic: bndr
description: "bndr: MIT Go one-binary Linux dashboard that finds loopback HTTP dev servers via /proc/net/tcp and bridges them onto the LAN; not adopted (shared host namespace = every login's ports incl. relay/agentd/InterWeave exposed, no auth, 0…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 58886dba556590de
---

## bndr: MIT Go one-binary Linux dashboard that finds loopback HTTP dev servers via /proc/net/tcp and bridges them onto the LAN; not adopted (shared host namespace = every login's ports incl. relay/agentd/InterWeave exposed, no auth, 0 stars); borrow socket->uid discovery for a FleetDeck 'what is serving' view, Host-header pinning, preview origin filter, installer shape

The bndr repository on GitHub (its author's personal account; read 2026-10-28 through moli). MIT, 12 commits, 0 stars, a v0.2.0 installer, and a self-written security audit dated 2026-10-24. It was ported from Node to Go: one static binary with the dashboard embedded, built for Linux x86-64 and ARM64.

**What it does:**
- Every 3 s it reads `/proc/net/tcp` and `/proc/net/tcp6` in its own network namespace and probes `GET /` with a 1 s timeout. Any HTTP answer qualifies.
- For each loopback listener it binds the LAN IP on the same port and proxies to it, carrying request bodies, streaming responses and WebSocket upgrades. A server already on the LAN gets a direct link.
- It shows a dashboard on port 4567 with cards named from the page title, rename and hide (keyed by port in `apps.json`), and JPEG thumbnails from one headless Chromium through chromedp, over a pipe rather than a debugging port.
- It doesn't care which agent or terminal started the server; Claude Code and Codex are its pitch.

**Its security model, stated honestly:**
- There is no authentication and no HTTPS. "Trusted LAN, use at your own risk", and the README warns that admin endpoints and secrets get exposed.
- Clients are limited to the subnet of the bound IP, judged on the source IP with forwarded headers ignored.
- The Host header must be the configured IP and port, which limits DNS rebinding.
- Thumbnails are restricted to the app's own scheme, IP and port, with a preview-only CSP and an 8 MiB cap. Setup fails closed, and the README says this is not an OS sandbox.
- `BNDR_EXCLUDE` keeps ports local; hiding a card doesn't.

**For the fabric: not adopted.**
1. **Shared namespace.** All about 30 logins on develop-qzapp share one network namespace. bndr run by any login would see and bridge every login's loopback listeners onto the LAN without auth, which crosses account boundaries the fabric keeps on purpose. That includes the relay, agentd and the control plane, InterWeave peers, and moli's unauthenticated CDP port from `moli serve`. An exclude list is the wrong default: a new fabric port would be exposed until someone remembered to add it.
2. **Wrong LAN.** This is a Qubes VM, so the "LAN" is the qube's network, not the owner's LAN, and the owner's devices reach it only through Qubes firewall rules.
3. **Maturity.** It is days old, has one author and no users.

**Where the need is real:** agents start dev servers (gzapp web clients, InterWeave dashboards), and the owner can't see them without asking. If wanted, build it allow-list first:
- discover from `/proc/net/tcp`, mapping the socket inode to its uid and then the login, so every port is attributed to its agent;
- show it read-only in FleetDeck, or as a `fabric-ctl <login> ports` query;
- expose only what a login explicitly publishes, never whatever is listening.

**Borrow:**
- socket-to-uid attribution as a host-load and disk-style fleet diagnostic ("who is listening where");
- Host-header pinning plus a source-subnet check on any fabric HTTP listener (the deck, agentd);
- a preview fetch confined to its origin, failing closed;
- the installer shape: SHA256SUMS from the same release, `--archive` offline install, a user unit without lingering, and an uninstall that keeps config. This matches install_fleetdeck.py's needs ([[fleet-deck-boot]]).

Related: [[moli-headless-browser]], [[trust-philosophy-uniform]].

*References: fleet-deck-boot, moli-headless-browser, trust-philosophy-uniform*

*Observed 2026-10-28 (fabric-coordinator)*
