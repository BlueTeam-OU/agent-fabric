# ADR-018 — Authority: one writer role per surface; a guard is hook + CI + suite; the read-only fence

**Date:** 2026-09-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** policies/AUTHORITY.md (the manual), policies/authority.json, policies/githooks/ (pre-commit, commit-msg, guarded-change.sh, locale-carve-out.sh), policies/check_agent_fabric_dir_authority.sh, policies/check_charter_authority.sh, policies/check_adr_amendment.sh, policies/ban_generated_by_attribution.sh, policies/check_repo_settings_carry_no_model_pins.sh, runtime/claude-code/bootstrap.sh (hook installation), .github/workflows/ci.yml, tests/run.sh, CLAUDE.md §"Read-only, unless you are fabric-coordinator"
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
Other roles read; what they need changed they propose — a pull request
they do not merge, or a message. The owning role per surface, for review
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

**One carve-out**: a locale's translations,
`identities/roles/<role>/locale/<suffix>/`, are committed by the holder
of `<role>` whose login is named for `<suffix>`, alone in their commit,
and merged by `fabric-coordinator`.

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
3. A merge that only folds a parent's guarded tree is no change of its
   own and passes; one that also edits the guarded tree is judged like
   any commit (`guarded-change.sh`).
4. `check_agent_fabric_dir_authority.sh` fails a branch whose added
   commits (merges aside) change a guarded path without the owner's
   trailer — every commit in agent-fabric, `.agent-fabric/**` in a
   project. It runs in `tests/run.sh` against `origin/main`, hence in CI
   on every pull request, merge-queue run and push to `main`.
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
7. A role proposing a change opens a pull request touching only the file
   in question, says what the role would take on or give up, and leaves
   it for the owning role; it never self-approves on the ground of being
   the only session that understands the surface.

## 6. Consequences

- Where the three parts stand:

  | guard | commit time | CI on the branch | suite |
  |---|---|---|---|
  | no machine attribution | `commit-msg` | `ban_generated_by_attribution.sh` (a CI step, and `tests/run.sh`) | `test_ban_generated_by_attribution.sh`, `githooks/test_hooks.sh` |
  | read-only fence, `.agent-fabric/` | `pre-commit`, `commit-msg` | `check_agent_fabric_dir_authority.sh` | `test_check_agent_fabric_dir_authority.sh`, `githooks/test_hooks.sh` |
  | decision records | `pre-commit` (`adr.py check` on the staged tree) | `check_adr_amendment.sh`, and `adr.py check` in lint | `tests/test_adr.py` |
  | charter authority by branch name | none | **not called** | `test_check_charter_authority.sh` |
  | no model pins in committed settings | none (the launcher refuses the same keys at launch) | not called here; gzapp's CI runs its own copy (`tools/checks/`) | `test_check_repo_settings_carry_no_model_pins.sh` |

- **Known gap — the branch-name tripwire has no call site.**
  `check_charter_authority.sh` is tested but nothing in this
  repository's CI runs it on a branch, though its header says the
  `pull_request` run is where it bites; the repository-wide fence (rules
  1–4) is what holds charters, briefs, the catalogue, the routing policy
  and `authority.json` today. Its one property the fence lacks — reading
  `authority.json` from the base of the diff, so a branch cannot appoint
  itself — is therefore not in force: the hooks read the checkout's own
  copy. Wiring it into `tests/run.sh`, or retiring it and its table rows
  in `policies/AUTHORITY.md`, is the open choice.
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
carve-out, the decision-record check at commit time.
`policies/AUTHORITY.md` stays the manual.

## References

- `policies/AUTHORITY.md`, `policies/authority.json`.
- `policies/githooks/pre-commit`, `policies/githooks/commit-msg`,
  `policies/githooks/guarded-change.sh`, `policies/githooks/locale-carve-out.sh`,
  `policies/githooks/test_hooks.sh`.
- `policies/check_agent_fabric_dir_authority.sh`,
  `policies/check_charter_authority.sh`, `policies/check_adr_amendment.sh`,
  `policies/ban_generated_by_attribution.sh`,
  `policies/check_repo_settings_carry_no_model_pins.sh`, and their tests.
- `runtime/claude-code/bootstrap.sh` (steps 4–5), `.github/workflows/ci.yml`,
  `tests/run.sh`.
- ADR-000 (P3), ADR-002 (role and login), ADR-003 (the binding),
  ADR-012 (the Doppler project is this role's).
