# CLAUDE.md — blueteam.brand's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of blueteam.brand's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

blueteam.brand has one role, brand-comms, and it is on the fleet's
coordination channel with the consumers it announces copies to: the
same relay and channel as blueteam.ee and the fabric itself
(`config.json` beside this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-10-19, at registration.

Three claims move together and this file is the authority for the
first: this status, the section in blueteam.brand's root `CLAUDE.md`
(`CLAUDE.snippet.md`, to be included there; the root file now carries
the inbox and skill lines only), and the session-start drain in
blueteam.brand's `.claude/settings.json`. The two in blueteam.brand are
pending: brand-comms-01 lands them in that repository after its
`.agent-fabric/` files. The token arrives with `fabric-secrets sync`
from the account's own store; the repository carries no env file for it.
