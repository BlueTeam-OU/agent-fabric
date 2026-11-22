# CLAUDE.md — blueteam-fabric's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of blueteam-fabric's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

blueteam-fabric's roles, fabric-coordinator and language-culture for
the locales, are on the fleet's coordination channel: the same relay
and channel as the fabric itself
(`config.json` beside this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-11-12, at registration.

Three claims move together and this file is the authority for the
first: this status, the section in blueteam-fabric's root `CLAUDE.md`
(`CLAUDE.snippet.md`, to be included there; the root file now carries
the inbox and skill lines only), and the session-start drain in
blueteam-fabric's `.claude/settings.json`. The two in blueteam-fabric are
pending: fabric-coordinator lands them in that repository with its
`.agent-fabric/` files. The token arrives with `fabric-secrets sync`
from the account's own store; the repository carries no env file for it.
