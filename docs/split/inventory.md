# The split's inventory (ADR-045)

Every top-level path of agent-fabric, classed by ADR-045 §5 rule 2: **engine** (code,
schemas, templates, routing defaults, guards, the engine's records — stays here and is
published), **instance** (the company that runs the agents — moves to the operator
repository, `gzapi-org/blueteam-fabric`, at stage 4), or **mixed** (split by amendment
at stage 4: the general part stays, the organisation's part moves). A client's
engagement (`gzapi-org/gzapi-engagement`, stage 5) takes nothing from here but the
project list it owns; project truth already lives in each project's own repository.

Engine code reads every instance path below only through `roots` (rule 1); the lint
that refuses a direct join is stage 2's last step. Kept current with the tree: a new
top-level path gets its row in the change that adds it.

| Path | Class | At stage 4 |
|---|---|---|
| `bin/`, `tools/`, `runtime/` (but `runtime/hosts/registry.json`) | engine | stays |
| `runtime/hosts/registry.json` | instance | operator: the hosts and placements |
| `tests/` | engine | stays; reads instance fixtures only (rule 3) |
| `communication/gzcoord/` (protocol, scripts, skills) | engine | stays |
| `routing/capabilities.json`, `effort.json`, `policies/`, `schemas/`, `shims*` | engine | stays (the defaults) |
| `routing/profiles.json` | instance | operator: our profile choices |
| `identities/schemas/`, `identities/prompt/` | engine | stays (prompt templates) |
| `identities/prompt/team.md` | mixed | the general working rules stay; our policy overlay moves |
| `identities/roles/` (catalogue, charters, briefs, locales) | mixed | a generic role library stays; the roles as we adapted them move |
| `identities/keys/`, `identities/agents/`, `identities/recovery.asc` | instance | operator: keys, lineage, agents, the recovery key |
| `policies/*.sh`, `*.py`, `githooks/`, the skill directories | engine | stays (the guards and skills) |
| `policies/authority.json`, `hygiene.json`, `auto-mode.json`, `bash-allowlist.json` | instance | operator (the allowlist moves with the policy it encodes) |
| `policies/AUTHORITY.md`, `code-as-memory.md` | mixed | the mechanism stays; our holders move |
| `projects/registry.json`, `projects/<id>/` | instance | operator (with `clients.json`, stage 3) |
| `projects/schemas/` | engine | stays |
| `memory/` (`domains/`, `shared/`, `agents/`) | instance | operator: our field knowledge |
| `memory/README.md`, `RUBRIC.md` | engine | stays (how a corpus works) |
| `docs/adr/` | mixed | numbers frozen (rule 4): engine records stay; organisation rules move by amendment into operator records that cite them |
| `docs/live-checks/` | instance | operator |
| `docs/fleet-deck/`, `docs/split/` | engine | stays |
| `docs/assets/` | engine | stays |
| `.agent-fabric/` (this repository's own remits and memory) | instance | operator |
| `.github/` | engine | stays (the engine's CI; the operator gets its own) |
| `.claude/` | engine | stays |
| `CLAUDE.md`, `README.md` | mixed | the engine's text stays; our working rules move to the operator's |
| `LICENSE`, `LICENSES/`, `REUSE.toml`, `.gitignore`, `ruff.toml` | engine | stays |
