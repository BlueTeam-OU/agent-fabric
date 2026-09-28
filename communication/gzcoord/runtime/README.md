# Runtime boundary

Runtime configuration belongs to the local agent instance, not to GZCOORD/1 messages.

It may contain:

- model provider and model name;
- subagent limits and capabilities;
- local tool permissions;
- local transport selection;
- process launch configuration.

A message may carry semantic `CAPABILITIES`, but it MUST NOT expose the concrete model/provider, local working directory, credentials, token budgets or subagent implementation details.

The stable logical identity is `host/instance`. A local filesystem path is never an address.

## Identity sourcing

The `instance` half of the address is the AGENT: the login of the
operating-system account the session runs under (`protocol/SPEC.md`
§3.1). The one implementation is agent-fabric's `runtime/identity.py`;
`scripts/gzmsg.mjs` asks it (`whoami()`) and falls back to the same
derivation (effective uid → login) when python is unavailable. The
working copy the session runs in is never an input — a session launched
from a directory named for another agent is still this login — and the
role is never an input either.

## Role sourcing

GZCoord keeps no role catalog of its own (`protocol/SPEC.md` §4) — the
deployment's is agent-fabric's `identities/roles/catalog.json`. The
`ROLE` a message carries MUST be the `id` (slug) of the role the agent
holds — `backend-dev`, `flutter-dev`, `architect-cto` — never its title;
a `TO-ROLE` MUST be a slug from the same file. The title stays in the
catalogue for reading. The address is not bound to the role: a
provisioned account is usually named for the role it was stood up as
(`architect-cto-01`, `backend-dev-02`), but a role can change without
the address changing (`protocol/SPEC.md` §4), and an account named
otherwise (`user`) is as much an agent as any. Which role the agent
holds is its runtime binding (`$AGENT_FABRIC_STATE_DIR/agents/<login>/
binding.json`), written by `tools/fabric/role.py` (`bin/fabric-role`, from a login shell) and read
through `whoami()`; `role.name`/`specialties`/`capabilities` in local
config follow the same source and are never authored independently of
it. `scripts/gzmsg.mjs` loads the catalogue from agent-fabric (or a
legacy `.roles/taxonomy.json` found by walking up from the working
directory) and enforces both slug rules, warning when an address names
a role other than the message's `ROLE`. A session's own identity
(`scripts/inbox.mjs` `identity()`, which the control plane's presence
also reads) derives the address from the login and host, the project
from the binding, and the role from the binding, else from a slug the
login carries — so the one spelling a peer can match is the default.
`recordedRole()` reports a binding that says nothing usable (unreadable,
or without a `role`) as a warning, and one naming a role the catalogue
does not have as an error, naming the file, because an agent
asserting a role the deployment does not know is a state to fix;
`identity()` takes only a role the catalogue has, and otherwise the
login's slug, if any. (The `hello` subcommand, which announced that
identity, is gone with the `HELLO` type it built: the type is retired,
and presence answers who is running.)
