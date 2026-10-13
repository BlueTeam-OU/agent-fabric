# ADR-039 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — the agent's repository is fabric-agent-<id>; its description names the login, never the id

The repository is renamed from `agent-fabric-secrets-<id>` to
`fabric-agent-<id>`, since it no longer holds secrets alone; the id stays
in the name, so a rename touches nothing. The description names host,
login and role so a listing is readable; the owner: "remove uuid from the
description, is already in repo name". The stores move from gzapi-org to
BlueTeam-OU by transfer and rename; GitHub's redirects serve the old names
meanwhile.
