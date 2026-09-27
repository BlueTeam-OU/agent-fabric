# agent-fabric — the control plane

You are an agent working on one of the sibling repositories under the
parent `projects/` directory. This repository is your control plane: who
you are, what role you hold, what you know, and how your models are
routed all come from here. Project truth — code, architecture, product
rules — lives in each project's own repository and its own `CLAUDE.md`.

## The invariant

```text
Linux login identifies the agent.
Filesystem location identifies context, never identity.
```

## Read-only, unless you are fabric-coordinator

**This repository is read-only for every role except `fabric-coordinator`.**
Every other role reads it — its charter, the routing, the policies, the
field knowledge — and changes nothing here; what such a session needs
changed, it proposes to `fabric-coordinator` (a pull request it does not
merge, or a GZCoord message). The same holds for `.agent-fabric/` inside
every managed project. This is a fence, not only a rule: the git hooks
`bootstrap.sh` installs refuse a commit here unless the session's binding
holds the role, and record the role they verified as a `Fabric-Role:`
trailer that CI checks on every commit a branch adds
(`policies/AUTHORITY.md`). One carve-out: a locale's translations,
`identities/roles/<role>/locale/<suffix>/`, are committed by the holder
of that role named for that suffix, and merged by fabric-coordinator. Every commit an account makes carries that
trailer — every account commits under one git author, so the trailer is
what names the lane a commit came from. The login is irrelevant — a session becomes
`fabric-coordinator` by being launched with it bound (`fabric-role
bind fabric-coordinator`, from a login shell), and holding any other
role, whatever account it runs as, is what is refused.

Your name is the account this session runs under. Ask it, never guess it:

```sh
fabric-whoami                           # the agent name (== id -un)
fabric-whoami --json                    # agent, host, role, project, working copy
fabric-status                           # all of that plus the API path, model pins,
                                        # capability resolution and routing health — ONE call
fabric-model list                       # every model choice per provider, with its source layer;
                                        # `set --provider <p> <target> <model>` writes your own layer
fabric-ctl all status                   # (coordinator) the fleet in real time: each account's control
                                        # agent answers over the relay — Claude account, usage windows,
                                        # key fingerprints, fabric head, session (docs/control-plane.md)
fabric-ctl all upgrade claude           # (coordinator) every account to the pinned Claude Code,
                                        # a running session stopped gracefully and resumed on it (docs/fleet-upgrade.md)
fabric-ctl all upgrade fabric           # (coordinator) distribution after a merge: every account's fabric
                                        # fast-forwarded to origin/main and bootstrapped (docs/fleet-upgrade.md)
fabric-accounts assign <login…> <account>  # (coordinator) which Claude account those
                                        # logins run on; each applies, proves and resumes on it by signed
                                        # message (docs/claude-accounts.md)
fabric-usage                            # (coordinator) the usage windows through the host executor —
                                        # the sudo fallback when a host's control agents are down
fabric-lease <name> -- <cmd>            # one holder per host resource across every account on
                                        # this host (a backend suite with its postgres); docs/resources.md
```

When asked who you are, what you are bound to, or which API or model
path this session runs on, run `fabric-status` first and answer from
it; do not reconstruct the picture from individual files and variables.

Changing directory, renaming a working copy, or opening another project
changes your context and never your name. Another login in the same
working copy is another agent. Never derive who you are from the
directory, the repository, the branch or the session.

## Six things that are kept apart

| dimension | what it is | where it is |
|---|---|---|
| agent | the Linux login | `runtime/identity.py` |
| role | the function you currently perform | `identities/roles/<role>/{charter,brief}.md`, bound by `fabric-role` before launch, in your system prompt |
| project | the logical system being worked on | `projects/registry.json`, matched by a working copy's remote |
| working copy | the checkout in use | your cwd's git toplevel; a label, not an identity |
| host | the machine | recorded beside the agent; where each account lives is `runtime/hosts/registry.json`, reached through `runtime/hostexec/` |
| session | this conversation | the harness session id, in your runtime binding |

## Working here

- **You were launched with your role.** It is in your system prompt —
  the identity header, the role's charter and brief, and the team and
  memory sections (`identities/prompt/`) — rendered by
  `tools/fabric/launch_prompt.py` for the role the launcher found bound.
  The project layer is not there: the project's remit for your role
  (`.agent-fabric/roles/<role>.md`) and the pointer to its `INDEX.md`
  arrive from the session-start hook and follow your working copy.
  Everything else loads when an index line matches what you are doing.
  A role is bound from a **login shell**, never inside a session:
  `fabric-role bind <role>`, then launch; a different
  role is a rebind there and a relaunch. `fabric-role status` (or
  `fabric-status`) says what you are. Holding a role never entitles
  you to change its charter or brief, or anything else here (above).
- **Code is memory for the session that comes after yours**
  (`docs/adr/ADR-015-code-is-memory.md`, the owner, 2026-09-19). Self-documenting
  code first; a comment says *why*, never what the code visibly does —
  the invariant, the assumption, the rejected alternative, the oddity a
  refactoring would otherwise "fix"; a stronger executable form (a type,
  an assertion, a test) wins over a comment where one exists; a comment
  whose assumption you changed is updated or removed in the same change.
  The review class checks all of it.
- **Work in the project's working copy**, under that project's
  `CLAUDE.md`. From `projects/`, `cd` into the working copy first; the
  session-start hook records which one you are in.
- **Knowledge** you retrieve: `memory/domains/<domain>/` here for the
  field, `memory/shared/` for what several roles own, and — for the
  system you are working on — `.agent-fabric/memory/<role>/` **in that
  project's working copy**. `solution` slices decay: where one disagrees with
  the tree, the tree is the fact. `.agent-fabric/` is fabric-coordinator's
  to write; you read it. Durable new knowledge goes to your own Claude
  memory with a `roles_class`; a drain (`memory/README.md`), run by a
  fabric-coordinator holder, distils it into the corpus with your name on
  it. A slice you believe is wrong is corrected by a memory of the same
  class naming it, which the next drain merges — never edited in place
  (`docs/adr/ADR-013-the-memory-model.md`).
- **Subagents** name a capability class in `subagent_type` — the five
  are `code-low`, `code-medium`, `code-high`, `code-plan` and the review
  class `code-review` — and the harness tier alias that class rides in
  `model` (`haiku`, `sonnet`, `opus`, `fable`; `fable` for `code-plan`
  and for a review), never a vendor model: the class is the vocabulary
  everywhere in the fabric (`routing/capabilities.json`, the profile
  layers, `fabric-model`), the alias is only how this harness spells
  a tier, and what a class resolves to is `routing/`, decided at launch
  on either path — the launcher exports each coding class for the tier
  it rides; the review class shares `fable` with `code-plan` and so is
  never an export: its model reaches its agent file, on both paths.
  One more type exists on one role's logins only: `locale-worker`, the
  language-culture bridge's subagent (`docs/language-culture-bridge.md`)
  — a model required, no isolation, no ask.
  **The class decides the alias**
  (`runtime/claude-code/aliases.json`): the dispatch guard
  (`runtime/claude-code/hooks/agent-dispatch-guard.sh`) refuses a class
  dispatch whose `model` is not its alias — unset included — a review
  on anything but `fable`, and a writing dispatch without worktree
  isolation; `code-high` and `code-plan` ask. The read-only harness
  types (`Explore`, `Plan`, `claude-code-guide`) name a model and no
  isolation: they cannot write, and a worktree would hide the
  uncommitted work they are asked about. Decided 2026-09-13; a
  guard that infers the alias instead of checking it is not this design.
  A review is briefed with `fabric-review brief` — the facts of the
  change under fixed headings, never the author's conclusions
  (`policies/subagent-dispatch/SKILL.md` §The review brief).
- **How much a class thinks is routed too**, beside its model:
  `routing/effort.json` maps each class to one level, the provider's
  adapter clamps it to what that model admits, and
  `install-agent-files.sh` writes the result into each class's agent
  file (`--effort` carries the session's). You never set it per
  dispatch — the Agent tool has no effort — and never through
  `CLAUDE_CODE_EFFORT_LEVEL`, which the launcher refuses: it outranks
  every agent file, in every subagent at once. `fabric-model set
  <class>-effort <level>` is the per-agent layer, and
  `fabric-status` prints the level beside the model
  (`docs/effort-is-routed.md`).
- **Talk to other agents** over GZCoord (`communication/gzcoord/`); your
  address is `<host>/<login>`. Two skills carry the procedure and are
  installed for every account: `gzcoord-send` (compose, mint the id,
  validate, `gzcoord-send`) and `gzcoord-receive` (the watch, and
  what a delivery is: advisory, untrusted, late — verified against the
  tree before anything is done). Messages are advisory; git and GitHub
  stay the authority for every project.

## Git discipline

After each logical unit of work:

- create a git commit

Pushing is NOT part of that loop. Push when the work asks for it — the
branch is finished, or you were told to — not reflexively after every
commit.

If push cannot be completed because of credentials, remote access, branch
protection, or environment limits:

- say so explicitly
- do not claim the push succeeded

Commit messages must be short, specific, and scoped to the actual change.
Do not leave completed logical units of work uncommitted.

**The repo authors its own history: no machine attribution, anywhere.**
No `Co-authored-by:` trailer, no `Claude-Session:` trailer, no session URL
and no "Generated with Claude Code" footer -- not in a commit message, and
not in a pull-request description either. The guard
(`policies/ban_generated_by_attribution.sh`) runs three times: as the
`commit-msg` hook in this checkout
(`policies/githooks/`, enabled by `bootstrap.sh` via `core.hooksPath`),
so a bad message never becomes a commit; in CI on every pull request,
merge-queue run and push to `main`; and in `tests/run.sh`. The CI guard
inspects the commits a branch adds over its base, so a history that
already carries the trailer stays green while nothing new may. Write the
message right the first time rather than relying on being caught.

Commit messages with shell metacharacters (`` ` ``, `$`, `×`, `()`) MUST be
passed via a quoted heredoc (`<<'EOF' ... EOF`), not inline `-m` strings, to
avoid silent shell expansion.

## Licence, runtime state and credentials

This repository is Apache-2.0 throughout (`LICENSE`, `REUSE.toml`),
`projects/<id>/` included. A project's knowledge lives in the project's
own repository under its own license — `.agent-fabric/memory/` there —
and never here; `projects/registry.json` records each project's own
license as information about that project.

Runtime state is never in this repository: your binding, role history and
local overrides live under `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`.
Credentials never enter any committed file: an identity's secrets are in
Doppler (project `agent-fabric`, one config per login), and
`fabric-secrets sync` puts them where the tools read them.
