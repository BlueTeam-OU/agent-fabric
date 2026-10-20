# ADR-062 — Each agent acts on GitHub as its own machine user

**Date:** 2026-10-20
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** which GitHub account each login acts as: its API calls, pushes, pull requests, reviews, armings and merges. How a machine user is made, named, recorded, credentialed and given access. How a login is cut over from the shared account, and what in the gate, the arm and provisioning changes with it. Not the git author or committer of a commit, which stays ADR-056's and ADR-057's (§5 rule 8). Not a GitHub App (§3)
**Pillar:** P1
**Evidence:** docs/live-checks/2026-10-20-github-one-account.md

## 1. Context and Problem

Every login acts on GitHub as one account: the owner's personal account,
through an OAuth token that `provision share` copies into every store and
`fabric-secrets sync` puts on each gh config. GitHub counts its primary
rate limit per user. On 2026-10-20 the fleet spent that one user's
5000 REST calls an hour and every gate read `review=?` until the reset.
More tokens of the same user add no quota.

The same token holds `admin:org`, `user`, `admin:public_key` and
`admin:ssh_signing_key`. So every session of every role can administer
both organizations and the owner's own account. That is more than any
role's lane needs, and more than a person in the same role would hold.

The tree assumes the one account in these places (the live check's read
at `068bacd7`):

- **Credentials.** `store_provision.py` `SHARED_NAMES` shares
  `GH_TOKEN`, the git author strings and one SSH key pair to every
  child. `secrets_sync.py` logs gh in with that token and writes that
  key to `~/.ssh/id_ed25519`, the key every `git@github.com` push and
  store push uses. ADR-012 §5 rule 4 and ADR-038 §5 rules 3 and 10 rest
  on it.
- **The review gate.** `post_review.py` marks the review class's review
  *because* every session posts as one account. `review_status/verdicts.py`
  counts a marked review as coverage only when its poster is the PR's
  author (or in `AGENT_FABRIC_REVIEW_POSTERS`). It counts an unmarked one
  as independent when its poster is not the author and is an owner,
  member or collaborator. ADR-020 §5 rules 6 and 7 rest on this.
- **The arm.** `arm.py` `author_of` takes authorship from the branch
  name, "the only evidence there is" under one GitHub login.
  `policies/AUTHORITY.md` and `charter_authority.py` say the same
  ("branch name self-declared").
- **Signing.** ADR-057 §5 rule 6 registers each agent's signing key on
  "the GitHub account that pushes the fleet's commits". GitHub verifies
  against the account that owns the committer email, which today is
  that same account.
- **Stores.** `store_enroll.py` creates each `fabric-agent-<id>` with
  the parent's gh, and the child pushes to it with the shared SSH key.
- **Attribution.** ADR-018 rejected CODEOWNERS, and ADR-026 and ADR-061
  attribute by branch, both because the account names no one.

No file maps a login to a GitHub user. GitHub's terms permit machine
accounts only when a human sets them up and answers for them, and they
allow one person "no more than one free machine account".

## 2. Decision

Each agent acts on GitHub as **its own machine user**: a GitHub account
the owner makes by hand for that agent, named for it, recorded in
`lineage.json` beside its key, holding a member's write access through
one team. Its token sits in the agent's own store and nowhere else. Each
agent then spends its own quota, and its pull requests and reviews carry
its own name on GitHub.

The commits do not change: the one shared author and committer stay,
and so the signing keys stay on the account that owns that email. A
change of pusher changes no signature's verification. Each agent as its
own commit author is a later decision (§7).

Logins are cut over one at a time. Each cut-over is read back. While any
login is not cut over, the shared token stays only in that login's
store, and `fabric-status` says so. After the last cut-over, the shared
token leaves the share list and the owner revokes it.

## 3. Alternatives Considered

- **More tokens of the shared user.** No quota gained: the limit is per
  user. It was the first thing ruled out.
- **A GitHub App.** One installation token per organization, with an
  installation's larger limit, short-lived tokens and no seats. It lost
  for three reasons. Every agent would still act as one bot identity, so
  the gate, the arm and attribution would keep their one-account
  workarounds. The installation's pool is still one pool, shared by the
  whole fleet in each organization. And the App's private key would be
  one more fleet-wide secret, the shape ADR-038 removed. It is the
  fallback if the terms question in §5 rule 2 cannot be settled.
- **A machine user per role group** (say, eight). It needs fewer seats
  and sign-ups, but holders of a role still share a pool and a name, and
  a role group is not an identity (ADR-002). Every rule keyed by a GitHub
  user would have to map it back to a set of logins.
- **Fine-grained personal access tokens.** A fine-grained token has one
  resource owner, and the fleet's repositories have three: both
  organizations and the owner's personal account. One token per owner
  per agent would triple the custody for no added control. A classic
  scope set with no `admin:` scope is the narrower thing in practice
  (§5 rule 5).
- **Each agent its own commit author now.** This would make GitHub's
  "Verified" name the agent, not the shared author. It moves every
  signing key, every author string and the ADR-056 rule all at once,
  and it is not needed for the quota. Deferred (§7).

## 4. Rationale

The quota is per user, so only more users fix it. A user per agent is
also the identity the fabric already has: the login is the agent
(the invariant), and its GitHub user becomes one more of its records,
like its key. The trust philosophy points the same way. A person
contributing to these repositories would have their own account with a
member's write access, not the organization owner's token. The same rule
for agents takes `admin:org` out of thirty stores.

Keeping commits as they are makes the change small where it is risky.
Signatures, the ruleset's `required_signatures` and ADR-057's checker
are untouched, and only what reads a GitHub *actor* changes: the gate,
the arm, provisioning, sync. The cut-over goes one login at a time and
each is read back, because a login whose token does not match its
recorded user would push and review as someone else.

## 5. Binding Rules

1. Each agent acts on GitHub as its own machine user, in every API call,
   push, pull request, review, arming and merge. It does so with a token
   of that user, held in its own store (ADR-038). No store holds another
   agent's token. Once a login is cut over (rule 11), no store of it
   holds the owner's personal token.
2. A machine user is made by the owner, by hand, and by no tool: GitHub
   forbids accounts registered by automated means. Before the first one
   is made, the owner settles the terms' one-free-machine-account limit.
   Either each machine user is on a paid plan, or GitHub's written answer
   is recorded in the live check. A user made before then is not cut
   over.
3. A machine user's GitHub name is the operator's prefix and the login:
   `blueteam-<login>` for this operator. Its display name is the agent's
   persona ("AI <First> <Surname>", ADR-039 §5 rule 8), and its profile
   names the role and the agent id. A login rename renames the user
   (ADR-039 §5 rule 6). The numeric GitHub user id, which a rename
   keeps, is what is recorded.
4. `identities/keys/lineage.json` records each agent's machine user as
   `github: {"user": <name>, "id": <number>}`, written by the parent. It
   is the only map from agent to GitHub user, and its schema says so. An
   agent with no user yet has no `github` field. A user's email address
   is one of the owner's, a different one per user. Each one is kept in
   fabric-coordinator's store settings beside the account metadata,
   never committed.
5. The password, the two-factor seed and the recovery codes of a machine
   user are the owner's, the human answerable for it, and none of them is
   in any agent's store. The agent holds only its token: a gh OAuth
   token or a classic token with the scopes `repo`, `workflow` and
   `read:org` (and `gist`, which `gh auth login` always adds). A token
   holding an `admin:` scope, `user` or `delete_repo` is refused at sync
   (rule 11).
6. Access: each machine user is a member of both organizations, and a
   member of one team, `fleet`, in each. The team has write on the
   managed repositories, and read on the settings and gateway
   repositories, as listed in the runbook. The owner's personal
   repositories admit the users as collaborators. Each agent's user has
   write on its own `fabric-agent-<id>`, and the parent's user has write
   on its children's. Organization administration stays the owner's.
   fabric-coordinator's user is admin on the fabric's own repositories
   only, for `repo_settings` and rulesets. Membership changes are made
   by hand and recorded in the runbook's table.
7. Git reaches github.com over HTTPS with gh as the credential helper
   (`gh auth setup-git`), so a push carries the agent's own token.
   Bootstrap rewrites `git@github.com:` remotes to HTTPS with
   `url.<https>.insteadOf`, and the recorded remotes are left as they
   are. Once every login is cut over, the shared SSH key pair leaves
   `SHARED_NAMES` and `~/.ssh/id_ed25519` and is removed from the
   owner's account.
8. Commits keep the one shared author and committer (ADR-056 §5 rule 8,
   ADR-057 §5 rule 7). The agents' signing keys stay registered on the
   GitHub account that owns the committer email. On acceptance, ADR-057
   §5 rule 6 is amended to say "the account that owns the committer
   email", not "the account that pushes".
9. A marked review (ADR-020) counts as coverage when its poster is a
   fleet machine user: any user `lineage.json` records, the PR's author
   included. An unmarked review or verdict comment by a fleet machine
   user is never an independent verdict. Both keep the gate's present
   behaviour under many users. `AGENT_FABRIC_REVIEW_POSTERS` stays for
   posters outside the fleet.
10. Authorship of a pull request stays its head branch's login, and is
    now checked as well. When that login has a machine user, the arm
    refuses a PR whose GitHub author is neither that user nor, for a
    branch named for the owner, the owner. The refusal names both.
    `--any-owner` keeps its present meaning. Dependabot's PRs are
    unchanged.
11. A login is **cut over** when its store holds its own token, `sync`
    has logged gh in with it, and `gh api user` answers the numeric id
    `lineage.json` records. Sync makes that check every run. It refuses,
    naming both ids, a token that answers another user, and one holding a
    scope rule 5 refuses. Until a login is cut over, `fabric-status`
    names it as still on the shared account. After the last cut-over:
    `GH_TOKEN` and the SSH key pair leave `SHARED_NAMES`, the owner
    revokes the shared token, and both organizations turn on their
    two-factor requirement.
12. Provisioning: a new agent is made with no `github` field, and
    `fabric-status` says it has no GitHub user. Its user is made by the
    owner (rule 2). Then the parent records it in `lineage.json` from
    the user's public profile, never from its token. The parent stores
    the token into the child's store from stdin, given by the owner at a
    terminal, and the child's next sync makes rule 11's check. Before the
    last cut-over, a new agent holds the shared token until then. After
    it, a new agent has no GitHub access until its user exists.
13. Quota is per machine user. A reader or poller that budgets GitHub
    calls (the j74 ledger) keys its ledger by the GitHub user, not the
    host.

## 6. Consequences

- Each agent has its own 5000 REST calls an hour and its own GraphQL
  points. A fleet-wide read, such as `fabric-errors` or `results.py`
  over every PR, spends the one user that runs it, so it is run by the
  role that needs it, and not spread across users to dodge the limit.
- The orgs take thirty seats, and each machine user's plan costs what
  rule 2 settles. The owner reads both numbers before the first sign-up.
- The owner makes, secures and answers for thirty accounts, and makes
  one more for each new agent. That is a manual step of provisioning,
  said by `fabric-status`, never skipped.
- GitHub now names who opened, reviewed and armed each PR. ADR-018's
  reason against CODEOWNERS and ADR-061's branch attribution can be
  revisited on that evidence (§7).
- No agent can administer an organization any longer. A task that needs
  it (a ruleset on a project repository, a team change) goes to the
  owner, as it would for a person in that role.
- Until the last cut-over, two kinds of login coexist. Every rule here
  states its behaviour for a login with no user yet, so the gate and the
  arm work across the mix.

## 7. Future Evolution

- **Each agent as its own commit author:** its machine user's noreply
  email as author and committer, and its signing key moved to its own
  user, so "Verified" names the agent. This amends ADR-056 §5 rule 8 and
  ADR-057 §5 rules 6 and 7, and it is proposed after the cut-over has
  run a week.
- CODEOWNERS (ADR-018 §3), and attribution by GitHub user in ADR-026 and
  ADR-061, once the users exist.
- A GitHub App beside the users, for fleet-wide reads only, if a single
  role's reads outgrow one user's quota.

## 8. Decision Status

Proposed, and parked. Its cost, about thirty Enterprise seats and
thirty paid plans, was judged too high, and the shared account stays.
The draft is kept for the day the quota or the cost changes. Until then
the quota is answered by spending less: the j74 ledger and budget-aware
polling. If taken up, it waits on the owner's acceptance and on the
owner's settling of §5 rule 2. On acceptance, ADR-012 §5 rules 4 and 8, ADR-018
§1, ADR-019 §5 rule 6, ADR-020 §5 rules 6 and 7, ADR-038 §5 rules 3 and
10, and ADR-057 §5 rule 6 are amended to point here. The owner's steps
are `docs/github-machine-users.md`. The tool changes are requested of
the contributor roles as their own jobs, in the order that file gives.

## References

- ADR-002 (role, login, model apart), ADR-012 (credentials), ADR-018
  (authority, CODEOWNERS), ADR-019 (PRs, the ruleset), ADR-020 (the
  marked review), ADR-026, ADR-061 (attribution), ADR-038 (each agent's
  store), ADR-039 (agent id, rename, persona), ADR-056, ADR-057 (author
  and signing).
- `tools/fabric/store_provision.py`, `tools/fabric/secrets_sync.py`,
  `tools/fabric/github/post_review.py`,
  `tools/fabric/github/review_status/verdicts.py`,
  `tools/fabric/github/arm.py`, `tools/fabric/store_enroll.py`,
  `tools/fabric/provisioning/github_signing_key.py`.
- `docs/live-checks/2026-10-20-github-one-account.md`,
  `docs/github-machine-users.md`.
