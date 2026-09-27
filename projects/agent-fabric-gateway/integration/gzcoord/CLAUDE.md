# CLAUDE.md — agent-fabric-gateway's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of the gateway's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

The gateway's one role, fabric-coordinator — the whole repository is
its (the gateway is the fabric's own data plane)
— is on the fleet's coordination channel: the same relay and channel as
gzapp, the site, InterWeave and the fabric itself (`config.json` beside
this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-09-24, the day the gateway became a managed project.

Three claims move together and this file is the authority for the
first: this status, the section in the gateway's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the session-start drain. The
gateway carries no `.claude/settings.json` of its own: its sessions are
the coordinator's, launched from the workspace, whose settings run the
drain and the watch for every working copy beneath it. The token
arrives with `fabric-secrets sync` from the account's own Doppler
config; the repository carries no env file for it.
