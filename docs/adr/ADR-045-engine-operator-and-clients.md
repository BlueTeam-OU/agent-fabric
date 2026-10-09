# ADR-045 — Engine, operator and clients

**Date:** 2026-10-08
**Status:** Accepted
**Ratified:** owner, 2026-10-09, in the coordinator's session ("accept adr 045"), carried by the pull request that marks it Accepted
**Decision Makers:** the owner (the three layers and the open engine); drafted by fabric-coordinator
**Scope:** what agent-fabric holds and what moves out of it: the engine (this repository, to be published), the operator repository of the company that runs the agents, and each client's engagement; the seam that lets one engine read either (`roots`, to be created by stage 2 as `tools/fabric/roots.py` and `runtime/control/roots.mjs`); how a working copy resolves to its client; decision-record numbering across the split
**Pillar:** P1

## 1. Context and Problem

agent-fabric is two things in one repository. One is the technology: the launcher, the control plane, GZCoord, the guards and the tools. The other is one organization's instance of it: its hosts, keys and lineage, its roles as adapted, its rulings, its memory corpus and its projects. Another company cannot use the first without inheriting the second.

A survey of the tree's 919 tracked files found:
- 475 engine files;
- 222 files of instance data;
- 222 files mixing both: the decision records, the charters and catalogue, the routing data and the team rules.

Of 44 decision records, 34 are engine and 10 mixed, and none is purely the organization's.

The engine reads instance data in about 85 places, through four styles of root resolution. One variable, `AGENT_FABRIC_ROOT`, means both "where the code is" and "where the organization's data is".

A second need comes from the work itself:
- the company that runs the agents (the operator) builds for clients;
- each client has rules for agents of its own;
- an agent moves between clients' projects in a day.

All the repositories live in one GitHub organization, the only one with a merge queue. So the organization cannot tell whose a repository is.

## 2. Decision

Three layers, each a repository:
- **The engine** is agent-fabric. It holds the code, the protocol, the guards, the schemas, the prompt templates, the routing defaults, a generic role library, and the engine's own decision records. It becomes public.
- **The operator** is a private repository of the company that runs the agents. It holds its hosts and placements, keys and lineage, its roles as it adapts them, its policies, its routing choices, its memory corpus, its rulings and decision records, and its list of clients.
- **Each client** has an engagement repository. It holds that client's rules for agents: its projects, coordination channel, secrets namespace and hygiene names. Its projects keep their own truth in their `.agent-fabric/`, as today.

The engine reads instance data only through one seam: `roots`, an engine root and an operator root. With no operator root configured, the engine's own tree is both, which is today's layout.

The client is resolved from the working copy, never from the GitHub organization:
- the working copy's remote leads to a project in the operator's registry;
- the project leads to its client;
- the client leads to its engagement.

Switching client is context, never identity, and needs no relaunch.

## 3. Alternatives Considered

- **Publish the repository as it is.** It would publish one organization's hosts, rulings and memory with the code, and no other company could run it without editing them out. Rejected.
- **Two layers: an engine and one instance per client.** The company running the agents is one and the same across clients: its hosts, keys, roles and knowledge do not belong to any client. Folding it into each client's instance would copy it into every one. Rejected.
- **The client from the GitHub organization.** Every repository sits in one organization for its merge queue, so the organization says nothing about whose it is. Rejected.
- **Renumber the records after the split.** About 330 files cite records by number, and other repositories cite 16 of them. Rejected: numbers are frozen (rule 4).

## 4. Rationale

- **The seam comes first, in one repository.** Every later stage is then a move of files behind an interface that already works both ways. The risky stage, moving the organization's content out, becomes a change of one root, read back on one account before the fleet.
- **The client resolves from the working copy.** That extends the invariant the fabric already keeps: the login is the agent, the filesystem is context. A client is more context.

## 5. Binding Rules

1. Engine code reads instance data only through `roots` (to be created as `tools/fabric/roots.py` and `runtime/control/roots.mjs`). `engine_root()` is the code's own location; until stage 4 it honours `AGENT_FABRIC_ROOT` when set, which every wrapper and fixture sets and which names that same location in production, and instance fixtures use `AGENT_FABRIC_OPERATOR`, never `AGENT_FABRIC_ROOT`. `operator_root()` is `AGENT_FABRIC_OPERATOR` when set, else the engine root. Lint refuses an engine module that joins an instance path itself.
2. Instance data is: the hosts and projects registries, `identities/keys/`, the role catalogue and the roles as adapted, `policies/*.json`, the routing overlays (`routing/profiles.json`), `memory/`, the organization's decision records, and `docs/live-checks/`. The engine keeps the code, the schemas, the templates, the routing defaults, the guards and the engine's records.
3. Engine tests read instance fixtures, never the live instance files, and the suite passes with `AGENT_FABRIC_OPERATOR` unset and set.
4. Decision-record numbers are frozen: no record is renumbered. A mixed record stays in the engine. Its organization-specific rules move out by amendment, into an operator record that cites it.
5. A working copy's client is resolved as remote → project (the operator's registry) → client → engagement, and never from the GitHub organization. Switching client changes the channel, the secrets namespace, the hygiene names and the client's rules in the session-start context, never the login or the role.
6. A client's credentials reach only that client's working copies. A client's project knowledge stays in that client's repositories; a drain refuses to carry it into the operator's corpus.

## 6. Consequences

- **The engine can be published,** and another company runs it with an operator repository of its own.
- **Every engine reader of instance data moves onto `roots`** (about 85 sites) before any file moves. That is stage 2: no behaviour changes, and the suite and lint output are unchanged.
- **Each account will hold two checkouts,** the engine and the operator. Bootstrap, the upgrade, the launcher's pull, the control agent's unit, moveto and new-agent learn both, and the operator pins the engine's version.
- **The key-trust anchor moves** to the operator's main branch with the keys.

## 7. Future Evolution

The stages that follow this record, each its own pull request:
- the seam;
- client resolution, with per-client secrets and channels;
- the extraction of the organization's content into the operator repository;
- the first client's engagement;
- publishing the engine, with a fresh history, a generic role library and an init command that creates an operator repository.

When the forge the fleet is evaluating offers a merge-queue equivalent, each company may hold its repositories there. The client layer needs no change, because it never relied on the GitHub organization.

## 8. Decision Status

Accepted; the inventory rule 2 applies is `docs/split/inventory.md`. Built so far:
- rule 1's seam exists (`tools/fabric/roots.py`, `runtime/control/roots.mjs`) and part of the readers use it; the rest move in stage 2, then its lint;
- rule 3: most tests read fixtures (`tests/stripped_run.py` runs a file on a copy without the instance files); a nightly run holds it;
- rule 2's list is applied by the extraction stage;
- rules 5 and 6, client resolution and the drain's refusal, come with the client stage.

Rule 4 holds today: no record has been renumbered.

## References

- ADR-001 (the records and their numbering), ADR-011 (a project's pin of the fabric), ADR-013 and ADR-014 (the memory corpus and its drain), ADR-038 and ADR-039 (keys, stores, the agent id), ADR-044 (identity kinds).
- `tools/fabric/layout.py`, `tools/fabric/workingcopy.py`, `runtime/control/gzcoord.mjs`: today's readers of instance data.
- `tools/fabric/lint_rules/docs.py` `project_name_findings`: the boundary lint the seam's rule extends.

## Amendments

The body above reads current; each change's full note is in [history/ADR-045-amendments.md](history/ADR-045-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-08 | The engine root honours AGENT_FABRIC_ROOT until stage 4 | §5 rule 1: a transition while wrappers and fixtures set it; instance fixtures use AGENT_FABRIC_OPERATOR |
