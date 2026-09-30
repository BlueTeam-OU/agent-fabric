# CLAUDE.md — InterWeave's use of GZCoord

The GZCoord agent communication protocol lives in agent-fabric
(`communication/gzcoord/`). This file covers the state of InterWeave's
integration with it, and the state is the first thing to know.

## GZCoord is ACTIVE — over the relay the coordinator hosts

InterWeave's roles — p2p-network-dev for the code, architect-cto for
its decision records and stage gates, devex-tooling for its CI — are on
the fleet's coordination channel: the same relay and channel as gzapp,
the site and the fabric itself (`config.json` beside this file), hosted
on the coordinator's workspace
(`projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`). Activated
2026-09-17, the day the CEO made InterWeave a managed project, before
the first session of its role was launched in a clone.

Three claims move together and this file is the authority for the
first: this status, the section in InterWeave's root `CLAUDE.md`
(`CLAUDE.snippet.md`, included there), and the hooks in InterWeave's
`.claude/settings.json` (the session-start drain among them). The token
arrives with `fabric-secrets sync` from the account's own
store; the repository carries no env file for it.
