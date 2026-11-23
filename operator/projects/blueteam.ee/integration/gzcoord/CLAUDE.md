# CLAUDE.md — blueteam.ee's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of blueteam.ee's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

blueteam.ee's owner role is brand-comms, with language-culture (review
of copy) and edge-hosting (the upload) beside it, and they are on the
fleet's coordination channel: the same relay and channel as gzapp and the
fabric itself (`config.json` beside this file), hosted on the
coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-10-10, at registration.

Three claims move together and this file is the authority for the
first: this status, the section in blueteam.ee's root `CLAUDE.md`
(`CLAUDE.snippet.md`, to be included there), and the session-start drain
in blueteam.ee's `.claude/settings.json`. The two in blueteam.ee are
pending: brand-comms-01 lands them in that repository after its
.agent-fabric/ remits (blueteam.ee#2). The token arrives with
`fabric-secrets sync` from the account's own store; the repository
carries no env file for it.
