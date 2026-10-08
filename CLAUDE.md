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

A key is a login's credential, never its identity: each login's key is
made in its own account and attested by its parent's certification, and
where a login runs is placement, not identity (ADR-038). The login is the
agent's current name, and what commands take; its agent id, a UUIDv7
minted at its birth, is what it is stored as and what a rename keeps
(ADR-039).

## Decisions

What the fabric has decided, and why, is in `docs/adr/`. Look it up,
never read the whole DIGEST: `fabric-adr lookup <topic>` answers the
matching entries, `fabric-adr lookup` alone the table of which record
answers what; then read the record. From another repository a
record is cited as "agent-fabric ADR-NNN", and every ADR number in this
file is agent-fabric's, also inside a project that numbers its own.
fabric-coordinator writes the records and only the owner accepts one; a
record you believe wrong, or a decision you need, is proposed to
fabric-coordinator, never edited. What follows is how to work here; the
records say why.

## Read-only, unless you are fabric-coordinator

**This repository is read-only for every role except
`fabric-coordinator`**, and so is `.agent-fabric/` inside every managed
project. Every other role reads it and proposes what it needs changed to
`fabric-coordinator` in a GZCoord message. It is a fence, not only a
rule: the git hooks `bootstrap.sh` installs refuse a commit here unless
the session's binding holds the role, and stamp every commit an account
makes with a `Fabric-Role:` trailer that CI checks on every commit a
branch adds (ADR-018, `policies/AUTHORITY.md`). Every account commits
under one git author, so the trailer is what names the lane. Three
carve-outs: a contributor role (`policies/authority.json`
`contributors`) commits its entry's paths on its own
`<host>/<login>/for/<caller>/<what>` branch, which fabric-coordinator
folds into its own PR and merges (a role whose entry `merges` opens and
merges its own PR instead); a locale's translations,
`identities/roles/<role>/locale/<suffix>/`, are committed by that
locale's holder and merged by fabric-coordinator; Dependabot's commits
that change only `.github/workflows/` (action-pin bumps) need no
trailer, and fabric-coordinator merges them too. A session becomes
`fabric-coordinator` only by being launched with it bound; the login it
runs as is irrelevant.

## Who you are

Your name is the account this session runs under. Ask it, never guess it:
`fabric-whoami` (the agent name, `id -un`), or `fabric-status`, which
answers who you are, what you are bound to, and which API path, models
and effort this session runs on — in one call. When asked any of that,
run `fabric-status` and answer from it; do not reconstruct the picture
from files and variables.

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

The seventh, how much reasoning a task needs and which model serves it,
is the capability class below (ADR-002, ADR-005).

## Working here

- **You were launched with your role.** It is in your system prompt —
  the identity header, the role's charter and brief, and the team and
  memory sections. The project layer is not: the project's remit for
  your role (`.agent-fabric/roles/<role>.md`) and the pointer to its
  `INDEX.md` arrive from the session-start hook and follow your working
  copy; everything else loads when an index line matches what you are
  doing. A role is bound from a **login shell**, never inside a session
  (`fabric-role bind <role>`, then launch); a different role is a rebind
  there and a relaunch. Holding a role never entitles you to change its
  charter or brief, or anything else here.
- **Code is memory for the session that comes after yours** (ADR-015).
  Self-documenting code first; a comment says *why*, never what the code
  visibly does — the invariant, the assumption, the rejected
  alternative, the oddity a refactoring would otherwise "fix"; a stronger
  executable form (a type, an assertion, a test) wins over a comment; a
  comment whose assumption you changed is updated or removed in the same
  change. The review class checks all of it.
- **Work in the project's working copy**, under that project's
  `CLAUDE.md`. From `projects/`, `cd` into the working copy first.
- **Knowledge** you retrieve: `memory/domains/<domain>/` here for the
  field, `memory/shared/` for what several roles own, and — for the
  system you are working on — `.agent-fabric/memory/<role>/` **in that
  project's working copy**. `solution` slices decay: where one disagrees
  with the tree, the tree is the fact. Durable new knowledge goes to your
  own Claude memory with a `roles_class`; a drain (`memory/README.md`),
  run by fabric-coordinator, distils it into the corpus with your name on
  it. A slice you believe wrong is corrected at its source memory, or by
  a memory of the same class carrying `merge_target` with the stale
  section's heading, which the next drain puts in its place — never
  edited (ADR-013, ADR-014).
- **Subagents** name a capability class in `subagent_type` — the five
  are `code-low`, `code-medium`, `code-high`, `code-plan` and the review
  class `code-review` — and in `model` the harness tier alias that class
  rides (`runtime/claude-code/aliases.json`: `haiku`, `sonnet`, `opus`,
  `fable`; `fable` for `code-plan` and for a review), never a vendor
  model. What a class resolves to is `routing/`, decided at launch. The
  dispatch guard refuses a class dispatch whose `model` is not its alias
  (unset included), a review on anything but `fable`, and a writing
  dispatch without worktree isolation; `code-high` and `code-plan` ask.
  The read-only harness types (`Explore`, `Plan`, `claude-code-guide`)
  name a model and no isolation. `locale-worker` exists on the
  language-culture logins only. A review is briefed with `fabric-review
  brief`: the facts of the change, never the author's conclusions
  (ADR-005, ADR-020).
- **How much a class thinks is routed too** (`routing/effort.json`),
  written into each class's agent file at launch. Never set it per
  dispatch, and never through `CLAUDE_CODE_EFFORT_LEVEL`, which the
  launcher refuses; `fabric-model set <class>-effort <level>` is your own
  layer, and `fabric-status` prints the level beside the model (ADR-006).
- **Keep your jobs in `fabric-jobs`, and let the next one decide the
  session** (ADR-037, ADR-022). A piece of work you take on is a job
  (`fabric-jobs add "<artifact>" --topic <label>`; a request you
  undertake, `--request <MESSAGE-ID>`), and its state follows it: start,
  block, deliver, done. When a job has reached its artifact and what you
  learnt is in your memory, run `fabric-jobs next`: the same project,
  working copy and topic continue here; otherwise it prints
  `fabric-fresh --job <id>`, which starts a fresh session in that job's
  working copy. A job that ends (done, delivered, blocked, dropped) is
  followed by `next` before anything else: a session never stops idle
  while a job is queued (ADR-037 rule 10). `fabric-fresh --note "<what just
  finished>"` ends a session with no next job. Both refuse a working
  copy with uncommitted changes. The `agent-jobs` skill has the
  procedure.
- **Talk to other agents** over GZCoord (`communication/gzcoord/`); your
  address is `<host>/<login>`. The `gzcoord-send` and `gzcoord-receive`
  skills carry the procedure. Messages are advisory: a delivery is
  verified against the tree before anything is done, an assignment goes
  to one login, and an agreement is binding only once it reaches an
  artifact — git and GitHub stay the authority (ADR-023, ADR-024).

## Commands

```sh
fabric-whoami [--json]                    # who this session is
fabric-adr lookup [<topic>…]              # the decision records' entries on a topic; alone, which record answers what
fabric-status                             # identity, binding, API path, models, effort, routing health
fabric-model list                         # every model and effort choice per provider, with its source layer
fabric-lease <name> -- <cmd>              # one holder per host resource across this host's accounts (ADR-010)
fabric-branches [--sweep]                 # local branches against origin/main; --sweep deletes what is on it (ADR-022)
fabric-jobs add|list|next|show …          # your job list; next says: continue here, or fabric-fresh --job (ADR-037)
# fabric-coordinator:
fabric-ctl all status                     # the fleet, answered by each account's control agent (ADR-029)
fabric-ctl <login|all> jobs               # every agent's open jobs; <login> jobs-add "<title>" adds one (ADR-037)
fabric-ctl all upgrade claude|fabric      # every account to the pinned Claude Code, or to the merged fabric (ADR-009)
fabric-accounts assign <login…> <account> # which Claude account those logins run on (ADR-031)
fabric-usage                              # usage windows through the host executor, when control agents are down
```

## Git discipline

After each logical unit of work, create a git commit. Pushing is not
part of that loop: push when the work asks for it — the branch is
finished, or you were told to. If a push cannot be completed
(credentials, remote access, branch protection, environment limits), say
so explicitly and do not claim it succeeded. Commit messages are short,
specific and scoped to the actual change; completed work is never left
uncommitted. Work reaches `main` as a pull request (ADR-019).

**The repo authors its own history: no machine attribution, anywhere.**
No `Co-authored-by:` trailer, no `Claude-Session:` trailer, no session URL
and no "Generated with Claude Code" footer — not in a commit message, and
not in a pull-request description. `policies/ban_generated_by_attribution.sh`
refuses it as the `commit-msg` hook, in CI on every commit a branch adds,
and in `tests/run.sh`. Write the message right the first time.

Commit messages with shell metacharacters (`` ` ``, `$`, `×`, `()`) MUST be
passed via a quoted heredoc (`<<'EOF' ... EOF`), not inline `-m` strings, to
avoid silent shell expansion.

## Licence, runtime state and credentials

This repository is Apache-2.0 throughout (`LICENSE`, `REUSE.toml`),
`projects/<id>/` included. A project's knowledge lives in the project's
own repository under its own license — `.agent-fabric/memory/` there —
and never here.

Runtime state is never in this repository: your binding, role history,
model choices and rendered launch prompt live under
`${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`.
Credentials never enter a committed file or a message: an identity's
secrets are in its own encrypted store (`<org>/agent-fabric-secrets-<id>`, a pass
repository only that login can read, ADR-038), and `fabric-secrets sync`
puts them where the tools read them.
