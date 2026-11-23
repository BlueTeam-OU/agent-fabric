# CLAUDE.md — gzapi.ge's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of gzapi.ge's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

gzapi.ge has one role, brand-comms, and it is on the fleet's
coordination channel with the agents it works beside: the same relay
and channel as gzapp and the fabric itself (`config.json` beside this
file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-09-16, when the account was read back deaf: a gzapi.ge session
drained nothing and could send nothing until this integration existed.

Three claims move together and this file is the authority for the
first: this status, the section in gzapi.ge's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the hooks in gzapi.ge's
`.claude/settings.json` (the session-start drain among them, wired
2026-09-16 in the site's PR #3). The token arrives with
`fabric-secrets sync` from the account's own store; the site's
tree carries no env file for it.
