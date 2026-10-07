# CLAUDE.md — radicle-spike's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of radicle-spike's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

radicle-spike's role, p2p-network-dev, is on
the fleet's coordination channel: the same
relay and channel as every other project of the fleet (`config.json`
beside this file), hosted on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-10-07, the day the spike became a managed project.

Three claims move together and this file is the authority for the
first: this status, the section in the spike's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the session-start drain,
which the account's user-scope settings run for every working copy. The
token is read from the account's own `secrets.env`; the repository
carries no env file for it.
