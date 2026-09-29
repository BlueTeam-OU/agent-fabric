# Authority

Decisions: agent-fabric ADR-018 (docs/adr/)

Who may change what in agent-fabric, and why that is not the same
question as who is currently doing what.

## The distinction

```text
an agent operating WITHIN a role's charter      -> the role's runtime binding
who may REDEFINE that charter                   -> a policy, attached to a role
```

An agent holds a role by binding it from a login shell (`bin/fabric-role`,
`tools/fabric/role.py`) and being launched with it: the launcher puts the
role into the session's system prompt, and nothing inside a session
changes it.
Holding a role gives the agent that role's remit for its work. It gives
the agent nothing over the role's definition: a `flutter-dev` instance
does not widen `flutter-dev`'s charter, and the account it runs under is
irrelevant to the question. Authority attaches to roles and to policy
files, never to Linux logins and never to directories, unless a policy
explicitly names one.

## The repository is read-only for every role but `fabric-coordinator`

Every file here — and `.agent-fabric/` in every managed repository — is
written only by a session whose binding holds `fabric-coordinator`.
Other roles read; a change they need is proposed to that role. The
table below says which role *owns* what, for the questions of review
and consent; who may *commit* is answered once, here, and enforced by
the fence and tripwire described under `.agent-fabric/` below, which
apply to this whole repository.

## The rules

| what | who may change it | how it is made visible |
|---|---|---|
| `identities/roles/<role>/charter.md` (any role) | `fabric-coordinator` | `policies/check_charter_authority.sh` |
| `identities/roles/<role>/brief.md` (any role) | `fabric-coordinator` — written from the holders' own accounts of the role (GZCoord replies), named in `origin` | `policies/check_charter_authority.sh` |
| `identities/roles/catalog.json` | `fabric-coordinator` | same |
| a project's taxonomy — where roles apply in its repository: `<working copy>/.agent-fabric/taxonomy.json` | `fabric-coordinator` | the `.agent-fabric/` fence and tripwire |
| `routing/policies/review-grade.json`, the review class's model | `fabric-coordinator` | same; `tools/fabric/lint.py` and `runtime/openrouter/launch` refuse a profile outside it |
| `policies/authority.json`, who holds `fabric-coordinator` | `fabric-coordinator` | same, read from the base side of the diff so a branch cannot appoint itself |
| `communication/gzcoord/protocol/*` | `fabric-coordinator` | the repository-wide fence and tripwire below: every commit here carries the role that made it, so a protocol change by any other role is refused at the keyboard and visible in CI; the charter states the rule in words |
| a managed project's architecture (gzapp: ADRs, contracts) | that project's roles (`architect-cto`) | the project's own guards, in its repository |
| a commit message or PR description (no machine attribution) | every agent, by writing it right | `policies/ban_generated_by_attribution.sh` on the commits a branch adds |
| a distilled slice under `memory/domains/`, `memory/shared/` | any agent, through a drain (`memory/README.md`) | `tools/fabric/lint.py` demands provenance |
| `.agent-fabric/` in a managed repository — the project's distilled knowledge (`memory/<role>/`) | the `fabric-coordinator` ROLE, whoever holds it: the drain writes it, every other role reads it | a fence at the keyboard — `policies/githooks/pre-commit` refuses the commit unless the binding holds the role, `commit-msg` records it as `Fabric-Role:` — and a tripwire in CI, `policies/check_agent_fabric_dir_authority.sh`, which reads that trailer; `lint.py` demands provenance |
| `recall.md` for a role | the role itself | authored, exempt from provenance; must stay under `identities/roles/` |

## The one carve-out: a locale's translations

`identities/roles/<role>/locale/<suffix>/` — a locale's rendering of
the role's charter, of the shared prompt sections and of the harness's
own text, its worker and its search locale — is authored by the holder
of `<role>` whose login is named for `<suffix>` (`language-culture-ge`
writes `locale/ge/`): the CEO's rule of 2026-09-17 that no text in a
locale has any author but its holder. The fence meets it halfway: a
commit that stages nothing but that subtree, from a session bound to
that role on that login, passes the pre-commit hook and is recorded as
`Fabric-Role: <role>`; CI admits such a commit for that subtree alone.
Anything staged beside it, another role, another suffix, an amend, is
refused as before, and the merge into `main` stays
fabric-coordinator's — the holder opens the pull request and does not
merge it. A merge the other way, `main` folded into such a branch, is
judged by what the branch adds over `main` (the ge holder,
2026-09-18: the index of a merge carries everything, and a translation
branch could never take `main` in once `main` had moved). Lint holds the
translation to its source (`tools/fabric/lint.py`, the digest, the
budget, every protected identifier), so what the carve-out admits is
prose in the locale, never a change to what a role is.

## `.agent-fabric/` in a managed repository

A project's knowledge lives in the project's own repository, under
`.agent-fabric/memory/<role>/` — versioned with the tree it describes,
under the project's license. Who may write it is the **role**, not the
account: a session launched with `fabric-coordinator` bound
(`bin/fabric-role bind fabric-coordinator`, from a login shell, then a
relaunch) may commit under `.agent-fabric/`; any other
session, whatever login it runs as, may not. The reason is the same as
for the corpus here: a slice is a claim with provenance, and the drain
is the only thing that makes one. A `backend-dev` session working in
gzapp reads `.agent-fabric/memory/backend-dev/` and may not edit it;
what it learns goes to its own Claude memory, and the next drain — run
by a session holding `fabric-coordinator` — distils it in with the
agent's name on it. A slice found wrong is corrected at the memory it
was drained from, or by a memory of the same class carrying
`merge_target` with the stale section's heading, which the next drain
puts in its place — never fixed in the slice (ADR-014).

This is the one rule with a **fence** rather than only a tripwire,
because the binding is readable where the commit is made: the git hooks
`bootstrap.sh` installs — in this checkout and in every registered
working copy (`policies/githooks/`) — refuse a commit that stages
`.agent-fabric/` in a project, or *anything* in agent-fabric itself,
unless the live binding holds the role, and write the role they
verified into the message as `Fabric-Role: fabric-coordinator`. CI
cannot read a binding, so `check_agent_fabric_dir_authority.sh` reads
the trailer on every commit a branch adds — under `.agent-fabric/**` in
a project, everywhere in this repository — a tripwire with the usual
limits: text anyone can type, `--no-verify` skips the hooks. It stops
the accident and makes the deliberate change visible. The login in the
branch name plays no part.

**Every commit carries the trailer, not only a guarded one** (since
2026-09-16). Every account commits under one git author, so the author
line says nothing about the lane; the branch name says it once and a
merge folds it away; the trailer travels with the message through
rebase, cherry-pick and `am`. `commit-msg` writes `Fabric-Role: <the
bound role>` on any commit whose account has a binding, and nothing on
one that has none — a fact about the account, never a claim it cannot
make. Only under guard is the role also checked against the owner; on a
code commit the trailer is attribution, not authorisation, and CI reads
it nowhere but under guard.

A merge commit that only folds a parent's `.agent-fabric/` — the routine
"update from main" after a drain — changes nothing of its own: the hooks
compare the staged guarded tree with each parent's and let it through
(with the folding account's role as its trailer, like any commit),
exactly as the CI tripwire skips merge commits. A merge
that also edits a slice by hand differs from both parents and is refused
like any other change (`policies/githooks/guarded-change.sh`).

## What the tripwire can and cannot do

`check_charter_authority.sh` reads the agent segment of the branch name
(`<host>/<agent>/<type>/<desc>`) and passes a recognised holder of
`fabric-coordinator`: a login listed in `policies/authority.json` (at the
base of the diff, never the branch's own copy) or an account named for the
role.
Every session pushes as the same GitHub account, so there is no identity
to check; the branch name is self-declared. This is a **tripwire**: it
stops the accident and the absent-minded edit, and it makes a deliberate
change visible in review. A session that means to route around it can,
by naming its branch differently, and nothing in this repository would
catch that. It also does not confuse the two questions above: an agent
named `flutter-dev-02` editing `flutter-dev`'s charter is refused, and so
is `architect-cto-01` — gzapp's architecture authority is not the control
plane's (`test_check_charter_authority.sh`).

## What did not weaken in the migration

- The charter and taxonomy authority rule, and its tripwire, moved from
  `tools/checks/` to `policies/`, widened to the catalogue, every
  project's taxonomy, the routing policies and the holders file. The
  owning role changed from `architect-cto` (the legacy repository's
  architecture role, which owned charters only because they lived there) to
  `fabric-coordinator`, the role whose remit is this repository.
- The review-grade gate moved from "the opus tier" to "the review
  capability" and is enforced in the same two places (lint on the
  committed files, the launcher on the merged result).
- The no-model-pins guard on committed settings is unchanged
  (`policies/check_repo_settings_carry_no_model_pins.sh`); the launcher
  fences the same scopes at launch and additionally refuses
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`.
- GZCoord's separation of identity claims from authentication is
  unchanged (the extraction record, kept in the project it was extracted from).
- The dispatch guard still denies a subagent with no model or no worktree
  isolation and asks on a premium model.

## An identity's secrets

Each agent's secrets are its own store, `<org>/agent-fabric-secrets-<id>`
(its agent id, ADR-039), encrypted to its key alone (ADR-038): the login writes and reads it; its parent,
the `fabric-coordinator` login that provisioned it, may add an entry
(`fabric-secrets store put`) and certifies its key, and reads nothing.
Making a key and store (`store-enroll.sh`), certifying keys
(`identities/keys/`), and the Claude-account templates in the
coordinator's store are `fabric-coordinator`'s. Until an account has
migrated, its secrets are in Doppler, as follows.

The Doppler project `agent-fabric` — one config per Linux login
(`<env>_<login>` under `agents`, `agents2`, …), holding
that login's credentials — is `fabric-coordinator`'s: creating a config,
migrating or rotating a value, issuing or revoking a service token
(`runtime/provisioning/secrets/enroll.sh`). An account holds a read-only
token for its own config and can see nothing else; `fabric-secrets sync`
refuses a config whose `AGENT_LOGIN` is not the login running it. No
value from that project ever enters this tree or a managed repository;
the guards that keep credentials out of commits apply unchanged.

## Proposing a change

Open a pull request touching only the file in question, say what the
role is being asked to take on or give up, and leave it for the role
that owns it. Do not self-approve on the grounds of being the only
session that understands the surface; that is the argument these rules
exist to refuse.
