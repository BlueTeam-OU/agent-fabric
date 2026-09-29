# CLAUDE.md — gzapp.decks's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of gzapp.decks's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

gzapp.decks has one role, brand-comms, and it is on the fleet's
coordination channel with the consumers it announces copies to: the
same relay and channel as gzapp, the site and the fabric itself
(`config.json` beside this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-09-17, at brand-comms's request, before the first session was
launched in the clone.

Three claims move together and this file is the authority for the
first: this status, the section in gzapp.decks's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the hooks in gzapp.decks's
`.claude/settings.json` (the session-start drain among them). The token
arrives with `fabric-secrets sync` from the account's own
store; the repository carries no env file for it.
