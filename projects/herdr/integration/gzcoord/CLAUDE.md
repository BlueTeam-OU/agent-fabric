# CLAUDE.md — herdr's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of herdr's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

herdr's role, rust-ui-dev — gzapi-org's fork of herdrdev/herdr, held
beside InterWeave — is on the fleet's coordination channel: the same
relay and channel as every other project of the fleet (`config.json`
beside this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-10-06, the day the fork became a managed project.

GZCoord is the fleet's channel, never herdr's own socket API: herdr's
agent-to-agent prompting stays unused between agents, which run as other
logins and cannot reach its socket.

Three claims move together and this file is the authority for the
first: this status, the section in the fork's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the session-start drain,
which the account's user-scope settings run for every working copy. The
token is read from the account's own `secrets.env`; the repository
carries no env file for it.
