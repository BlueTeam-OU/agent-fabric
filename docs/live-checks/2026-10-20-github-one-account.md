# 2026-10-20 — the fleet acts on GitHub as one account

Run by fabric-coordinator, as the login user (job j309, ADR-062). At 06:18Z that morning the fleet's REST quota read core 0/5000 while GraphQL still had 4593, and every gate printed `review=?` until the reset. The question here: what one GitHub account the fleet uses, what it may do, what GitHub allows, and what in the tree depends on there being only one.

## What was measured

From this login, with the token `fabric-secrets sync` put on its gh config, so the same one every login holds (`provision share`):

- `gh api user`: the login `andreabenetton`, type `User`, the owner's own personal account.
- `gh auth status`: an OAuth token (`gho_` shape), scopes `admin:org`, `admin:public_key`, `admin:ssh_signing_key`, `gist`, `read:enterprise`, `repo`, `user`, `workflow`.
- `gh api rate_limit` at 09:40Z: core 4194/5000 and GraphQL 4992 left, after the reset. One pool: GitHub counts the primary limit per user, across all of that user's tokens.
- `orgs/BlueTeam-OU` and `orgs/gzapi-org`: plan `enterprise`, filled seats 2, two-factor requirement **off**, default repository permission `read`. Members: `andreabenetton` alone in each. BlueTeam-OU has one outside collaborator, and neither org has a team.
- `projects/registry.json` remotes: 34 on `gzapi-org`, 20 on `BlueTeam-OU`, 6 on the owner's personal account, the rest upstreams the fleet only reads.
- `agent-fabric`'s ruleset `main protection`: no bypass actors; `required_signatures`; required check `ci-ok`; `required_approving_review_count` 0. `agent-fabric` is public.
- GitHub's Terms of Service (docs.github.com, site-policy, read with moli): "Accounts registered by 'bots' or other automated methods are not permitted. We do permit machine accounts: … set up by an individual human who accepts the Terms on behalf of the Account, provides a valid email address, and is responsible for its actions … You may maintain no more than one free machine account in addition to your free Personal Account."
- GitHub's commit signature verification (docs.github.com, read with moli) verifies a signature against the account that owns the commit's committer email, never against whoever pushed it.
- `identities/keys/lineage.json`: 30 agents, 30 distinct logins, the longest 20 characters. It records no GitHub user for any agent. No file in the tree maps a login to a GitHub user.

A read of the tree at `068bacd7` listed every place that assumes the one account. ADR-062 §1 names them.

## What it decides

- One account means one quota. More tokens of that user add nothing, so the quota grows only with more users (ADR-062 §2).
- Every login holds the owner's own token, `admin:org` included. A machine user per agent also takes that power out of every store.
- Thirty free machine users made by one person break GitHub's terms. Each needs a paid plan, or GitHub's written word, before the first sign-up (ADR-062 §5 rule 2).
- "Verified" follows the committer email. So pushing as another user leaves every signature as it is while the commits keep the one shared author, and ADR-057's keys stay where they are.
- The orgs' two-factor requirement can be turned on only after every member has two-factor, machine users included.

## Not verified

- Whether a paid seat in the Enterprise org makes a machine user "not free" under the terms. The plan reads it the strict way and asks for a paid personal plan or GitHub's answer.
- The seat price, and whether an outside collaborator on a private repository takes a seat on this plan.
- Whether an Enterprise org raises a user's own REST limit above 5000/h. Read it from a machine user's first `rate_limit`.
