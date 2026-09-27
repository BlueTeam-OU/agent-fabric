# agent-fabric

The infrastructure through which people and agents build **enduring
organizations**: teams that learn from their work, keep their expertise
when their tools change, and take responsibility within a mandate the
humans set. Today it is the control plane for the Claude Code agents that
work on the repositories beside it — identities, roles, memory, model
routing, agent-to-agent communication, policy — and holds nothing about
what any project builds. What it is for, pillar by pillar, and how much
of each exists today: [ADR-000](docs/adr/ADR-000-the-enduring-organization.md).

```text
Linux login identifies the agent.
Filesystem location identifies context, never identity.
```

```text
project repositories contain project truth
agent-fabric contains agent infrastructure
```

## Decisions

What the fabric has decided, why, and what would reopen it lives in
[`docs/adr/`](docs/adr/README.md): numbered decision records, amended in
place with their history kept, checked by `tools/fabric/adr.py` in the
commit hook, in CI and in the suite. Read
[`docs/adr/DIGEST.md`](docs/adr/DIGEST.md) first, then the record.

- fabric-coordinator writes the records; only the owner accepts one, and
  an `Accepted` record names where the owner's word is.
- Another role that wants a decision changed proposes it to
  fabric-coordinator (a GZCoord `REQUEST`, or a pull request it does not
  merge).
- Outside this repository a record is cited as "agent-fabric ADR-NNN".

## What is kept apart

What must endure is kept apart from what must be able to change
([ADR-002](docs/adr/ADR-002-role-login-and-model-are-kept-apart.md)).
Never collapse these: an agent keeps its name across roles, projects,
working copies, hosts and sessions; two agents in one working copy are
two agents; a role is held by any number of agents at once.

| dimension | the question | where the answer lives |
|---|---|---|
| **agent** | Which Linux user is this agent? | `runtime/identity.py` (the effective user, nothing else); `bin/fabric-whoami` |
| **role** | What function is it performing now? | `identities/roles/<role>/` (charter, brief, recall, skills), `identities/roles/catalog.json`; bound before launch from a login shell (`bin/fabric-role bind`), carried in the system prompt |
| **project** | Which logical system is it working on? | `projects/registry.json`, matched from a working copy's remote |
| **working copy** | Which checkout is in use? | the cwd's git toplevel: a label, not an identity |
| **host** | Which machine is the account on? | `runtime/hosts/registry.json`, reached through `runtime/hostexec/` and `bin/fabric-host` ([ADR-010](docs/adr/ADR-010-hosts-provisioning-host-execution-and-resources.md)) |
| **session** | Which conversation is this? | the harness session id, in the runtime binding ([ADR-003](docs/adr/ADR-003-per-agent-state-is-one-layer.md)) |
| **capability and model** | How much reasoning does a task need, and which model serves it now? | `routing/capabilities.json` classes: `code-low`, `code-medium`, `code-high`, `code-plan`, `code-review`; layered per role and login by `routing/profiles.json`, with a routed effort in `routing/effort.json` ([ADR-005](docs/adr/ADR-005-models-are-routed-by-capability-class.md), [ADR-006](docs/adr/ADR-006-effort-is-routed.md)) |

## What it is made of

| part | what it does | where | decided in |
|---|---|---|---|
| **memory** | knowledge by scope (the field, the system, the individual) and kind, written by whoever learnt it and drained with provenance | `memory/` here for the field and what roles share; `<working copy>/.agent-fabric/memory/<role>/` in each project for that system ([manual](memory/README.md)) | ADR-013, ADR-014 |
| **communication** | agents talk to each other over GZCOORD/1, an advisory protocol; the address is `<host>/<login>` | `communication/gzcoord/` | ADR-032, ADR-033 |
| **control plane** | a control agent per account answers signed actions over the relay, with no model session needed: status, presence, fleet upgrades, account moves | `runtime/control/`, `bin/fabric-ctl`, `bin/fabric-accounts` | ADR-009, ADR-029, ADR-030, ADR-031 |
| **routing** | a capability class resolves to a provider's model, a family shim where one is needed (`routing/shims.json`), and an effort level | `routing/`, `bin/fabric-model` | ADR-005, ADR-006, ADR-007 |
| **harness adapter** | the launcher, hooks, agent files and settings that turn all of the above into a Claude Code session, on plain Claude or through OpenRouter | `runtime/openrouter/launch`, `runtime/claude-code/` | ADR-008, ADR-022 |
| **project binding** | which roles, domains and path rules apply to each managed repository, and each role's remit there | `<working copy>/.agent-fabric/` in the project (`taxonomy.json`, `roles/`); the fabric's own under `.agent-fabric/` here | ADR-004, ADR-011 |
| **policy and guards** | who may change what, enforced by a commit hook, a CI check and a suite case | `policies/` | ADR-018, ADR-019, ADR-020 |
| **credentials** | per-login secrets in Doppler, put where the tools read them; never in a file here or in a message | `bin/fabric-secrets` | ADR-012 |
| **hosts and resources** | provisioning an account, running a command on its host, one holder per shared host resource | `runtime/provisioning/`, `runtime/hostexec/`, `bin/fabric-lease` | ADR-010 |

## How a session starts

```sh
agent-fabric/bin/fabric-role bind <role>          # from a login shell, once per role change
agent-fabric/runtime/openrouter/launch            # through OpenRouter
agent-fabric/runtime/openrouter/launch --provider anthropic   # on plain Claude
```

The launcher reads the binding, renders the role's launch prompt
(identity, charter, brief, the team and memory sections), resolves every
capability class to a model and an effort for the chosen provider,
writes them into the agent files, and starts the session with its
message watch armed; the settings `runtime/claude-code/bootstrap.sh`
writes for the account start it in auto mode. `projects/CLAUDE.md`, written by
`runtime/claude-code/bootstrap.sh`, imports `agent-fabric/CLAUDE.md`;
the SessionStart hook records the working copy and project and returns
that project's remit for the role. Nothing inside a session changes its
role: a different role is a rebind and a relaunch. Every sibling
repository keeps its own `CLAUDE.md`; `projects/` is not a git
repository.

## Runtime state and credentials

Never in this repository. Per agent, under
`${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`:
`binding.json` (role, project, working copy, session, host),
`role-history.jsonl`, `model-profile.local.json` (the agent's own model
choices; `bin/fabric-model`) and the rendered `launch-prompt.md`, every
one written through `runtime/identity.py`. An identity's secrets are in
Doppler, one config per login, and `bin/fabric-secrets sync` puts them
where the tools read them.

## Commands

```sh
bin/fabric-status          # who this session is, its binding, API path, models, effort, routing health — one call
bin/fabric-whoami          # the agent name (== id -un)
bin/fabric-role            # bind, status, list (from a login shell)
bin/fabric-model list      # every model and effort choice per provider, with its source layer
bin/fabric-ctl all status  # the fleet, answered by each account's control agent (coordinator)
bin/fabric-review brief    # the facts of a change for a blind review
bin/fabric-lease <name> -- <cmd>   # one holder per host resource
```

## Provenance

Every distilled slice records who learned it (`agent`), where (`host`,
`working_copy`), what it applies to (`project`, the role, the class) and
when (`distilled_at`, the observation hashes). A slice from before the
login model carries an old `clone_id` label that nothing resolves any
more.

## Origin

This infrastructure began inside one managed repository and was
extracted with `git filter-repo` into a control plane of its own; before
it went public its history was rewritten so that no commit carries that
project's knowledge or names its internals. What the extraction record
explained, the decision records now state. `docs/live-checks/` holds
what was measured live here: the evidence the records cite.

## Tests

```sh
tests/run.sh            # static checks, python suites, GZCoord, bash suites and guards
tests/run.sh static     # bash -n over every script, shellcheck (errors), ruff (ruff.toml)
```

CI (`.github/workflows/ci.yml`) runs the static checks once and the whole
of `tests/run.sh` on Python 3.12, 3.13 and 3.14 with Node 22, and once
more on Python 3.12 with Node 20 — the oldest interpreters the tools
promise to run on — and the static, python and bash suites in a Fedora
and a Debian container that install the fabric's host contract from the
platform profile's own package map (`runtime/provisioning/platform/`),
so the map is proven by being used. Locally a missing shellcheck or ruff
is said, not passed over. A test run leaves nothing behind it did not
find ([ADR-021](docs/adr/ADR-021-a-test-run-leaves-nothing-it-did-not-find.md)).

## License

**Apache-2.0**, throughout (`LICENSE`; `REUSE.toml` assigns nothing else,
and `reuse lint` passes). A managed project's knowledge lives in the
project's own repository (`<working copy>/.agent-fabric/memory/`) under
that project's license and is never here; `projects/<id>/` holds a
project's binding and integration material, which is this repository's.
`projects/registry.json` records each project's own license as
information. `tools/fabric/lint.py` refuses a second license in
`REUSE.toml`, a project with no stated license, and any project
knowledge under `memory/projects/`.
