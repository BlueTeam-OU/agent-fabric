# ADR-018 — Authority: one writer role per surface; a guard is hook + CI + suite; the read-only fence

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** policies/AUTHORITY.md (the manual), policies/authority.json, policies/githooks/ (pre-commit, commit-msg, guarded-change.sh, locale-carve-out.sh), policies/check_agent_fabric_dir_authority.sh, tools/fabric/guards/contributors.py, policies/check_charter_authority.sh, policies/check_adr_amendment.sh, policies/ban_generated_by_attribution.sh, policies/check_repo_settings_carry_no_model_pins.sh, runtime/claude-code/bootstrap.sh (hook installation), .github/workflows/ci.yml, tests/run.sh, CLAUDE.md §"Read-only, unless you are fabric-coordinator"
**Pillar:** P3

## 1. Context and Problem

When the control plane was extracted from the first managed project on
2026-09-13, two questions that had been one came apart: who is doing a
piece of work, and who may redefine the rules that work runs under. A
`flutter-dev` session is entitled to work within `flutter-dev`'s charter;
nothing entitles it to widen that charter — and the charter, the brief
and the recall guide are exactly the files lint cannot protect, because
they are authored rather than distilled and so exempt from provenance.

Every session pushes as the same GitHub account and commits under one git
author, so neither CODEOWNERS nor the author line can tell one session's
lane from another's. The one place the question "does this session hold
the role" can be answered for real is the keyboard, where the session's
runtime binding is readable (ADR-003). A rule stated only in prose had
already been lost whenever a session changed; a guard that ran only in
CI could be seen only after the push.

## 2. Decision

**Authority attaches to roles and to policy files, never to Linux logins
and never to directories**, unless a policy names one. Holding a role
gives the agent that role's remit for its work and nothing over the
role's definition.

**agent-fabric is read-only for every role but `fabric-coordinator`**,
and so is `.agent-fabric/` in every managed repository.
Other roles read; what they need changed they propose — a message, or a
contributor's branch (A 2026-10-01). The owning role per surface, for review
and consent, is `policies/AUTHORITY.md`'s table; who may *commit* is one
answer for the whole repository.

**The fence and the tripwire.** The git hooks `bootstrap.sh` installs in
this checkout and in every registered working copy refuse, at the
keyboard, a commit that stages anything in agent-fabric — or anything
under `.agent-fabric/` in a managed project — unless the live binding
holds `fabric-coordinator`; `commit-msg` writes the role it verified as a
`Fabric-Role:` trailer. CI cannot read a binding, so
`check_agent_fabric_dir_authority.sh` reads that trailer on every commit
a branch adds — here on every commit, in a project under
`.agent-fabric/**` — a tripwire: it stops the accident and makes a
deliberate bypass visible.

**Every commit carries the trailer**, guarded or not:
it is what names the lane a commit came from, since the author line
cannot.

**Two carve-outs for a role.** A locale's translations,
`identities/roles/<role>/locale/<suffix>/`, are committed by the holder
of `<role>` whose login is named for `<suffix>`, alone in their commit,
and merged by `fabric-coordinator`. A contributor role — one
`policies/authority.json` names under `contributors` — commits, in
agent-fabric itself, the paths its entry lists and none it excludes, on
a contributor branch of its own; `fabric-coordinator` folds that branch
into its own pull request and merges it (A 2026-10-01), unless the entry
`merges`, when the role carries its own pull request (A 2026-10-07). What a role *is*
and what enforces the fence — identities, routing, policies but the bash
allowlist, the protocol, the records, the guards and what they import or
run — is never in an entry, and lint holds every entry to that.

**A guard is three things or it is not a guard** (the coordinator's
brief): a check at commit time where the fact is readable, a
check in CI over every commit a branch adds, and a case in the suite
that plants the violation.

## 3. Alternatives Considered

- **Authority by login** (the account named `fabric-coordinator` may
  write). Rejected: a role moves between accounts (ADR-002); the account
  a session runs under says nothing about what it was launched to do.
- **CODEOWNERS or GitHub review rules.** Not available: every session
  pushes as one GitHub account.
- **A CI check alone.** Rejected as the only line: CI sees only what the
  commit declares, after the push. The hook is the fence because the
  binding is readable there; CI is the tripwire behind it.
- **The branch name as identity** (`check_charter_authority.sh`, the
  first guard). Kept as a tool, but self-declared text, folded away by a
  merge; the repository-wide fence replaced it as the working guard.
- **The architecture role owning charters** (the legacy layout). Changed
  on extraction: `fabric-coordinator` is the role whose remit is this
  repository; a project's architecture authority is not the control
  plane's.

## 4. Rationale

Operating within a role is separate from the power to redefine it
(ADR-000, P3). A fence where the fact is readable and a tripwire where it
is only declared together make an accidental change impossible and a
deliberate one visible, without pretending to more: a session that
types a trailer or passes `--no-verify` can route around both, and the
record says so rather than claim otherwise.

## 5. Binding Rules

1. Every file in agent-fabric, and `.agent-fabric/` in every managed
   repository, is committed only by a session whose runtime binding holds
   the role `policies/authority.json` names (`fabric-coordinator`); the
   login and the directory play no part.
2. `policies/githooks/pre-commit` refuses a commit staging such a path
   unless the binding holds the role; `commit-msg` refuses the same
   commit and writes `Fabric-Role: <role>` on every commit whose account
   has a binding, and nothing on one that has none. `bootstrap.sh` sets
   `core.hooksPath` in this checkout and every registered working copy.
3. A merge changes only the guarded paths where it differs from the
   clean three-way merge of its parents (`git merge-tree --write-tree`),
   compared with renames off; without a clean merge (an octopus, an old
   git) it is judged against every parent. A fold of main is therefore no
   change of its own and passes, even when both sides moved the guarded
   tree; a conflict resolution, a hand edit, or keeping one side's tree
   where the other moved it is judged like any commit
   (`guarded-change.sh`).
4. `check_agent_fabric_dir_authority.sh` fails a branch whose added
   commits, merges judged as rule 3 says, change a guarded path without
   the owner's trailer — every commit in agent-fabric, `.agent-fabric/**` in a
   project. CI's verdict is main's copy of it, run isolated
   (`python3 -I`) as a step before any of the branch's code, on every
   pull request, merge-queue run and push to `main`; `tests/run.sh` runs
   the branch's copy against `origin/main` as the local check
   (A 2026-10-01).
5. The carve-out: a commit staging only `identities/roles/<role>/locale/<suffix>/`,
   from a session bound to `<role>` on a login named for `<suffix>`,
   passes both hooks and is recorded as `Fabric-Role: <role>`; CI admits
   it for that subtree alone. Anything staged beside it, another role,
   another suffix, or an amend, is refused; the merge into `main` stays
   `fabric-coordinator`'s.
6. A guard on committed content has a commit-time check where the fact is
   readable, a CI check over every commit a branch adds, and a suite case
   that plants the violation. The attribution ban, the read-only fence
   and the decision-record checks each have all three (§6 for the rest).
7. A role proposing a change sends it to the owning role — a message
   naming the file, the change, and what the role would take on or give
   up — and leaves it there; a contributor may instead deliver it on a
   contributor branch within its entry (rule 8). The fence refuses any
   other role's commit, so "a pull request it does not merge" is a step
   only a contributor can take. It never self-approves on the ground of
   being the only session that understands the surface (A 2026-10-01).
8. The contributor carve-out: a commit from a session bound to a role
   `policies/authority.json` names under `contributors`, on a branch
   `<host>/<login>/for/<caller>/<what>` of that login, staging only
   paths its entry lists (a rule ending in `/` is a directory, any other
   one file, no globs) and none it excludes, passes both hooks and is
   recorded as `Fabric-Role: <role>`; CI admits it against the entry as
   the BASE has it, so a branch cannot widen its own; the hooks read it
   as HEAD has it. A guarded commit whose message types a role other
   than the binding is refused. Moves are judged by source and
   destination; an amend with nothing staged, an amend of another role's
   commit, a half-written entry, another role and `.agent-fabric/` in a
   project are refused as before; lint refuses an entry that reaches a
   definition or the fence. The decision is
   `tools/fabric/guards/contributors.py`, one module for the hooks and
   CI. The contributor opens no pull request; the coordinator folds the
   branch unrebased and merges (A 2026-10-01) — unless its entry carries
   `"merges": true`. Such a role also commits on its own branch
   `<host>/<login>/<type>/<what>` and opens, blind-reviews, arms by the
   team's count rule and merges its own pull request within its entry;
   what lies outside the entry reaches that pull request as the
   coordinator's commits, and the coordinator distributes the merge. CI
   refuses a pull request opened from a `for/` branch, and one in which
   no commit declares the owner role unless a contributor role in it
   merges its own work, which may fold another contributor's supply as
   the coordinator does; which login holds a role is never committed, so
   the declared roles are judged (A 2026-10-08).

## 6. Consequences

- Where the three parts stand:

  | guard | commit time | CI on the branch | suite |
  |---|---|---|---|
  | no machine attribution | `commit-msg` | `ban_generated_by_attribution.sh` (a CI step, and `tests/run.sh`) | `test_ban_generated_by_attribution_cli.py`, `tests/test_githooks_cli.py` |
  | read-only fence, `.agent-fabric/` | `pre-commit`, `commit-msg` | `check_agent_fabric_dir_authority.sh`, main's copy run isolated (ci.yml); `tests/run.sh` the local check | `test_check_agent_fabric_dir_authority.sh`, `tests/test_githooks_cli.py` |
  | the contributor carve-out | `pre-commit`, `commit-msg` (`contributors.py hook`) | `check_agent_fabric_dir_authority.sh`, main's copy, against the base's entry | `tests/test_contributors.py` |
  | decision records | `pre-commit` (`adr.py check` on the staged tree) | `check_adr_amendment.sh`, and `adr.py check` in lint | `tests/test_adr.py` |
  | charter authority by branch name | none | main's copy run isolated against `origin/main` (ci.yml); `tests/run.sh` the local check (A 2026-09-28) | `test_check_charter_authority_cli.py` |
  | no model pins in committed settings | none (the launcher refuses the same keys at launch) | not called here; gzapp's CI runs its own copy (`tools/checks/`) | `test_check_repo_settings_carry_no_model_pins.sh` |

- The branch-name tripwire runs in CI: `tests/run.sh` calls
  `check_charter_authority.sh` against `origin/main` on every branch, so
  its one property the fence lacks — reading `authority.json` from the
  base of the diff, so a branch cannot appoint itself — is in force
  beside the hooks, which read the checkout's own copy (A 2026-09-28).
- The fence depends on every account's last bootstrap; an account whose
  hooks are unset commits unguarded until the next, and the CI tripwire
  then refuses the branch.
- Anyone can type a trailer and `--no-verify` skips the hooks: the fence
  stops accidents, not intent.

## 7. Future Evolution

P3's direction states the mandate as a whole — what an agent decides
alone, what needs the role's owner, what needs the owner's word; this
record is one of the pieces it would gather. Signed commits per account
would turn the trailer from a declaration into a proof; not planned.

## 8. Decision Status

Accepted and in force: the read-only repository and the `.agent-fabric/`
fence, the merge fold, the trailer on every commit, the locale
and contributor carve-outs, the decision-record check at commit time.
`policies/AUTHORITY.md` stays the manual.

## References

- `policies/AUTHORITY.md`, `policies/authority.json`.
- `policies/githooks/pre-commit`, `policies/githooks/commit-msg`,
  `policies/githooks/guarded-change.sh`, `policies/githooks/locale-carve-out.sh`,
  `tests/test_githooks_cli.py`.
- `policies/check_agent_fabric_dir_authority.sh`,
  `policies/check_charter_authority.sh`, `policies/check_adr_amendment.sh`,
  `policies/ban_generated_by_attribution.sh`,
  `policies/check_repo_settings_carry_no_model_pins.sh`, and their tests.
- `runtime/claude-code/bootstrap.sh` (steps 4–5), `.github/workflows/ci.yml`,
  `tests/run.sh`.
- ADR-000 (P3), ADR-002 (role and login), ADR-003 (the binding),
  ADR-012 (credentials are this role's), ADR-038 (each login's store,
  and the coordinator as every child's parent).

## Amendments

The body above reads current; each change's full note is in [history/ADR-018-amendments.md](history/ADR-018-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-28 | The charter tripwire runs on every branch | §6: `check_charter_authority.sh` called from `tests/run.sh`; the known gap closed |
| 2026-09-30 | Doppler is retired: the stores replace it | References |
| 2026-10-01 | A contributor role commits its entry's paths | §2, §5 rules 7–8, §6, §8: a role named under `contributors` commits its entry's paths on its own contributor branch; the coordinator folds and merges |
| 2026-10-01 | The fence's own code stays out; a guarded commit declares its binding | §2, §5 rule 8: the hooks read HEAD's entry; a typed role other than the binding is refused; the fence's own code is never in an entry; lint compares by prefix |
| 2026-10-01 | CI judges a branch with main's guards | §5 rule 4, §6: CI's authority verdict is main's copy of the guards, run isolated before the branch's code; `tests/run.sh` keeps the branch's copy as the local check |
| 2026-10-04 | A merge is judged on its own change | §5 rules 3–4: a merge's own change is what differs from the clean three-way merge of its parents, at the hooks and in CI; CI no longer skips merges |
| 2026-10-07 | A contributor that merges its own pull request | §5 rule 8: an entry's `merges` lets its role open, review and merge its own pull request within its entry; CI refuses a pull request from a for/ branch, and a contributor-only one whose role does not merge |
| 2026-10-08 | A role that merges its own work may fold another contributor's supply | §5 rule 8: a PR with no owner-role commit passes when a role in it merges its own work |
