# GZCoord

GZCoord is a small, transport-agnostic, human-readable messaging protocol for autonomous software-development agents collaborating on the same Git/GitHub-governed project.

This directory is agent-fabric's communication subsystem (`communication/gzcoord/`): the protocol, its reference runtime and tests. It is not a source of authority for any project's state. Project-specific integration — how one managed repository hosts a relay, what its `CLAUDE.md` says, how it installs the hooks — lives with that project under `projects/<project-id>/integration/gzcoord/`.

## Boundary

- **Git/GitHub** are authoritative for source, branches, commits, PRs, reviews, merges, conflicts, ADRs and history.
- **A message is never committed.** The channel is coordination, not
  record: a `MESSAGE-ID` may be *cited* in a commit or PR body, but the
  messages themselves stay out of the repository — the durable,
  ordered record is the relay, and committing chatter would make every
  message a blocking artifact while 14 sessions collide on one file.
  What a message *decides* is not decided until it lands in the
  artifact it concerns — the PR body, the commit body, the contract's
  `change_summary`, the ADR — citing the id. A decision that lives only
  on the channel is a decision nobody can hold.
- **Repository `CLAUDE.md`** governs how agents operate on the repository.
- **GZCoord** defines identity, role announcement, discovery, addressing and human-readable message semantics.
- **Transport adapters** deliver messages. **The current transport is a Claude-Bridge relay** hosted on the developer host by the fabric-coordinator's working copy (a project's integration says where: `projects/<id>/integration/gzcoord/`), drained at session start by `scripts/inbox.mjs`; when the relay is down, a person copies messages between session terminals (`docs/HUMAN-RELAY-TRANSPORT.md`). The first automated attempt before the relay is retired (`history/telegram-transport/`); how the relay was selected is `history/claude-bridge-selection/`. The interface an automated adapter must satisfy is `docs/TRANSPORT-ADAPTER-CONTRACT.md`.
- **Local runtime config** contains model/provider and subagent policy; those values are not sent in messages.

## Identity

Every agent instance has the logical address:

```text
<host>/<instance>
```

Example:

```text
develop-gzapp/architect-cto
```

The address is logical, but it is not arbitrary: `host` is the machine's short hostname and `instance` is the login of the operating-system account the session runs under — the agent, as agent-fabric's `runtime/identity.py` resolves it (`protocol/SPEC.md` §3.1). The working copy the session is in is context, never identity: rename it, move it, or open another project and the address stays. The derivation runs one way. The address is not a filesystem path or a home directory, and no peer may reconstruct one from it or act outside its own working copy.

## Discovery and presence

Every message carries its sender's `ROLE`, so any message says who holds
what. Whether an agent is online is presence, and presence is the
deployment's to answer, never an announcement (`protocol/SPEC.md` §5):
`HELLO` and `GOODBYE` are deprecated. In agent-fabric the control plane
answers it from each account's process table —
`bin/fabric-ctl <login|all> presence` — and `scripts/send.mjs` asks it
before a `TO` or `TO-ROLE` message leaves (`docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md`).

## Normal message

```text
[GZCOORD/1] REVIEW
FROM: develop-gzapp/backend-dev
ROLE: backend-dev
TO: develop-gzapp/architect-cto
PROJECT: gzapp
BRANCH: feature/stop-resolution
COMMIT: a81c142
SUBJECT: Stop resolution contract change

CONTEXT:
The passenger and advertising flows currently represent the resolved
stop differently.

REFERENCES:
- github-pr: #184
- path: contracts/common/stop-resolution.yaml

REQUEST:
Please review the architectural impact before merge.
```

The message is parseable, but it remains readable without tooling.

## Sending and receiving, as a session

`scripts/send.mjs <file>` posts one message: normalized, validated last,
refused when `FROM` is not the session's own address, resolved (relay,
channel, token) exactly as `scripts/inbox.mjs` resolves the inbox.
`scripts/inbox.mjs` drains at session start and, with `--follow`, is the
session-long watch (`--wait [S]` is a bounded read for a reply you expect). The procedures around them — when a message is the
right instrument, how to address it, what a delivery is and is not — are
two skills every account has: `skills/gzcoord-send/SKILL.md` and
`skills/gzcoord-receive/SKILL.md` (installed user-scope by
`runtime/claude-code/bootstrap.sh`).

## Local configuration

There is none to write by hand. Who a session is comes from the OS
login and its runtime binding (`runtime/identity.py`; `role.name` and
`specialties` from the role it holds, slugs from agent-fabric's
`identities/roles/catalog.json` — GZCoord keeps no separate role
catalog; see `runtime/README.md` "Identity sourcing" and "Role
sourcing"). Which relay and channel a session uses comes from its
project's integration (`projects/<id>/integration/gzcoord/config.json`),
or from `CLAUDE_BRIDGE_URL` and `GZCOORD_CHANNEL` in the environment;
with neither, nothing is joined. The token comes from the account's
synced secrets (`fabric-secrets sync`). Model, provider and subagent
limits are the launcher's (`runtime/openrouter/`), not part of GZCOORD/1.

## Integration

1. Keep this directory where it is: agent-fabric is the control plane, and every managed repository uses the same copy.
2. Add the project's snippet to its root `CLAUDE.md` — gzapp's is `projects/gzapp/integration/gzcoord/CLAUDE.snippet.md`.
3. Configure the project's transport (gzapp's relay: `projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`); a project with no integration joins nothing.
4. Validate messages with `node communication/gzcoord/scripts/gzmsg.mjs validate <file>`.

`protocol/SPEC.md` is the normative protocol; the layout is the section
above. How the relay was chosen is `history/claude-bridge-selection/`.
