# ADR-002 — Role, login and model are kept apart

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/identity.py, bin/fabric-whoami, bin/fabric-role and tools/fabric/role.py, tools/fabric/launch_prompt.py, runtime/openrouter/launch, runtime/claude-code/hooks/session-start.sh, identities/ (roles, catalog.json, prompt/, agents/)
**Pillar:** P1
**Evidence:** docs/live-checks/2026-09-15-append-system-prompt.md

## 1. Context and Problem

The control plane began inside one managed repository, where an agent was
known by its clone (`clone_id`). A clone, a directory, a branch or a
session is something that changes under running work; an identity that
rides on one of them breaks each time it does. On 2026-09-13 the fabric
moved to one invariant: the Linux login identifies the agent, and the
filesystem location identifies context, never identity.

The role had the same problem a second way. Until 2026-09-15 a session
bound its own role from inside the harness with a `/role <role>` slash
command, which wrote the binding and printed a "load now" list for the
model to Read. That depended on the model obeying an instruction printed
into its context and on nobody compacting it away; a role could be
switched under a running session, so what the session believed and what
its binding said could silently disagree; and nothing recorded what a
session had been launched as. The same shape had bitten that day in
another dimension: a session launched on the previous model default kept
it for hours, because a session's model is fixed at exec.

## 2. Decision

These dimensions are kept apart, and none is derived from another:

| dimension | what it is | where it is |
|---|---|---|
| agent | the Linux login of the effective user | `runtime/identity.py`, `bin/fabric-whoami` |
| role | the function the agent currently performs | `identities/roles/<role>/` (charter, brief, recall), `identities/roles/catalog.json`; bound before launch, carried in the system prompt |
| project | the logical system being worked on | `projects/registry.json`, matched from a working copy's remote |
| working copy | the checkout in use | the cwd's git toplevel; a label, not an identity |
| host | the machine | recorded beside the agent; `runtime/hosts/registry.json`, reached through `runtime/hostexec/` |
| session | this conversation | the harness session id, in the runtime binding |
| capability and model | how much reasoning a task needs, and which model satisfies it now | `routing/capabilities.json`, `routing/profiles.json`, `routing/effort.json` |

The role is bound **from a login shell, never inside a session**
(`bin/fabric-role bind <role>`), and **rides in the system prompt**:
`runtime/openrouter/launch` renders `launch-prompt.md` for the bound role
(`tools/fabric/launch_prompt.py`) and passes it as
`--append-system-prompt-file` on both launch paths. The project layer — the
role's remit in that project and the pointer to its `INDEX.md` — follows
the working copy and arrives from the SessionStart hook.

This table is the canonical separation. `CLAUDE.md` lists the first six;
`README.md`'s longer table adds the fabric's other axes (memory,
communication, project binding, compatibility shims, runtime adapter),
which are subsystems, not facets of who an agent is.

## 3. Alternatives Considered

- **Identity from the clone, directory or branch** (the `clone_id` era).
  Rejected: every rename or second checkout made a new "agent"; two logins
  in one working copy looked like one.
- **An environment variable or a registry of agents.** Rejected: the
  operating system is the registry; `identities/agents/` deliberately
  assigns nothing, and `current_agent()` has no environment override.
- **Binding the role inside the session (`/role`).** Rejected 2026-09-15
  for the three failures in §1; the command is deleted and `bootstrap.sh`
  removes the copy it once installed.
- **The project remit in the launch prompt.** Rejected: a session changes
  project with `cd`; the project layer must follow the cwd of the moment.

## 4. Rationale

What survives a change is exactly what was kept apart from the thing that
changed (ADR-000 §4): a role moves between accounts with its knowledge, a
model family is replaced under running work, a host crashes, and the
agent's name and history stay put. Carrying the role in the system prompt
makes it present from the first request, through every compaction, and
uneditable from inside; a byte-stable file keeps the harness's prompt
prefix cacheable, so a changed digest means changed content.

## 5. Binding Rules

1. The agent's name is `id -un` of the effective user, resolved only by
   `runtime/identity.py` (or `bin/fabric-whoami`, which execs it). No tool
   derives it from the directory, repository, branch, project, session or
   an environment variable.
2. Nothing committed assigns an agent name to a directory, clone, branch
   or session; `identities/agents/<login>.json`, where present, is
   descriptive only and never consulted to decide who an agent is.
3. A role is bound only from a login shell: `bin/fabric-role bind`, and
   `tools/fabric/role.py` beneath it, refuse when `CLAUDECODE`,
   `CLAUDE_ENV_FILE` or `AGENT_FABRIC_LAUNCH_PROFILE` says a session is
   running. A different role is a rebind and a relaunch.
4. The launch prompt carries, in order: the identity header, the role's
   charter, its brief, `identities/prompt/team.md` and
   `identities/prompt/memory.md`. It carries no project, no timestamp, no
   session id and no cwd, and renders the same bytes for the same (agent,
   host, role).
5. Agent, host and role are never parameters of the render: they come
   from the OS and the binding. The launcher refuses a caller's own
   `--system-prompt*` / `--append-system-prompt*`, as it refuses
   `--settings`.
6. The launcher stamps `AGENT_FABRIC_LAUNCH_ROLE` and
   `AGENT_FABRIC_LAUNCH_PROMPT_DIGEST`; `bin/fabric-status` prints
   `launched as <role>` and a `DRIFT` line when the binding, the session
   default or the prompt file moved under the session. A rebind is never
   silent.
7. A binding is per (agent, host): `read_binding` refuses one naming
   another agent or written on another host (review, 2026-09-16). A move
   between hosts is a rebind there.
8. The **brief** (`identities/roles/<role>/brief.md`) is written without
   identifiers — no PR, record, migration or message number, no repository
   path; the **remit** (`.agent-fabric/roles/<role>.md` in the project)
   carries the anchored version. A role with no brief launches with the
   placeholder `identities/prompt/brief-missing.md`.
9. A role's charter, brief and distilled knowledge belong to the role, not
   the login; holding a role never entitles a session to change them.

## 6. Consequences

- `fabric-whoami` / `fabric-status` answer "who am I", never a guess from
  the tree; another login in the same working copy is another agent.
- A role survives compaction; switching it costs a relaunch.
- The rendered prompt has a character ceiling (`MAX_CHARS` in
  `tools/fabric/launch_prompt.py`) that every role's charter and brief
  share, rendered for every role by `tests/test_launch_prompt.py`.

## 7. Future Evolution

Not read back on 2026-09-15: whether the appended text survives `/compact`
in place (it is part of the system prompt, re-sent every request).
`--system-prompt-snapshot on` may ride along; nothing depends on it.
Briefs were written from the roles' own accounts (broadcast
`01a0a594-3719-76b1-97d6-fb8c67e520fd`, 2026-09-15); a role that did not
reply has none until one is written under the same rule, and the wishes
that went to neither brief nor remit are a backlog for the roles owning
those surfaces.

## 8. Decision Status

Accepted and in force: the login model since 2026-09-13, the role at
launch since 2026-09-15 (the owner's decision of that day), per-host
bindings since 2026-09-16.

## References

- `runtime/identity.py` (module docstring: identity, state layer, per-host
  binding), `bin/fabric-whoami`, `bin/fabric-status`.
- `bin/fabric-role`, `tools/fabric/role.py`, `tools/fabric/launch_prompt.py`,
  `tests/test_launch_prompt.py`, `runtime/openrouter/launch`,
  `runtime/claude-code/hooks/session-start.sh`.
- `identities/roles/catalog.json`, `identities/prompt/`,
  `identities/agents/README.md`, `identities/schemas/binding.schema.json`.
- `docs/live-checks/2026-09-15-append-system-prompt.md`; `docs/presence.md`
  (whether a session exists is the control plane's `presence`, not an
  announcement from the launcher).
- ADR-000 (P1); ADR-001 (how this record changes). The state layer, adding
  a role, and model routing are the records that follow this one.
