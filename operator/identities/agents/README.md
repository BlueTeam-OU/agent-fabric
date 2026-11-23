# identities/agents/

An agent is a Linux login. There is deliberately no registry of agents
here: the operating system is the registry, `runtime/identity.py` reads
it, and nothing committed may assign an agent name to a directory,
clone, branch or session.

What this directory may hold, per login, is optional descriptive
metadata an operator wants to keep with the control plane — a display
name, contact, the host an account was provisioned on, standing notes —
as `identities/agents/<login>.json`. None of it is consulted to decide
who an agent is, and nothing here is required for an agent to exist.

Per-agent runtime state (the role currently bound, the working copy in
use, the session) is never committed; it lives under
`${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`
(`identities/schemas/binding.schema.json`).
