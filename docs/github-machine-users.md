# GitHub machine users — the owner's steps and the build order

This is how ADR-062 is carried out: what the owner decides, what the
owner does for each user, which tool changes come in what order, and
the table of who is cut over. The record says why. This file says how,
and it changes as each step lands.

## 1. What the owner decides first

None of these is the fabric's to decide, and no user is made before all
four are answered.

1. **The terms' free-account limit** (ADR-062 §5 rule 2). GitHub allows
   one person "no more than one free machine account". Choose one:
   - **a.** Each machine user on GitHub Pro. This is the strict reading
     and needs no answer from GitHub. The cost is thirty plans.
   - **b.** Ask GitHub support whether a user that holds a paid
     Enterprise seat counts as "free", and wait for the written answer.
   - **c.** If neither is acceptable, the fallback is a GitHub App
     (ADR-062 §3), which reopens the record.
2. **Seats.** Both orgs are on Enterprise, and each member takes a seat:
   thirty members means thirty more seats. Read the price on the
   enterprise's billing page.
3. **Email.** One address of yours per user, each different (an alias
   per login, say). They are kept in fabric-coordinator's store
   settings, never committed.
4. **The name prefix.** `blueteam-<login>` is proposed, for example
   `blueteam-python-dev-04`. The longest login gives 29 characters, under
   GitHub's 39. Check that the prefix is free, by making the pilot user
   below.

## 2. For each user (the owner, by hand)

A tool cannot do these steps: GitHub refuses automated sign-up.

1. Sign up in a private browser window as `<prefix><login>`, with that
   login's address. Choose the plan from §1.1.
2. Turn on two-factor (TOTP). Keep the password, the TOTP seed and the
   recovery codes in your own password manager, never in an agent's
   store (ADR-062 §5 rule 5).
3. Profile: the display name is the persona (`fabric-persona <login>`),
   and the bio is "machine user of agent-fabric: <role>, agent
   <agent id>". The avatar is the persona's.
4. Accept the invitations fabric-coordinator prepares: to both orgs and
   to the `fleet` team. The owner sends them, because inviting takes org
   admin.
5. Make the token. Either run `gh auth login --web` as that user with
   scopes `repo,workflow,read:org` (gh adds `gist` itself), or make a
   classic token with those three scopes. No `admin:` scope, no `user`,
   no `delete_repo`: sync refuses them.
6. Hand it over at a terminal, on the line fabric-coordinator gives. It
   pipes the token into the login's store on stdin
   (`provision github <login>`, still to be built, step 3.3).
   fabric-coordinator then reads back the login's next sync.

## 3. Build order (tool changes, each a contributor's job)

Each step lands as its own job and PR, in this order. A step is done
only when its live read-back is in `docs/live-checks/`.

1. **Schema and record.** `lineage.json` gains `github: {user, id}` and
   its schema says it is the only map (rule 4). This is fabric-coordinator's
   own: identities are on the never-list.
2. **Sync's check.** `secrets_sync.py` compares `gh api user`'s id with
   the record and refuses another user, or a scope outside rule 5,
   naming both. `fabric-status` and `fabric-ctl all status` say whether
   a login is cut over, on the shared account, or has no user (rules 11
   and 12). For python-dev.
3. **The store write.** `provision github <login>` records the user from
   its public profile, writes the token from stdin into the child's
   store, and is never shared (rule 12). `new-agent` records "no GitHub
   user" and prints the owner's §2 steps. For python-dev.
4. **HTTPS git.** Bootstrap runs `gh auth setup-git` and adds the
   `insteadOf` for `git@github.com:` (rule 7). This includes store
   pushes in `store_enroll.py`. `bootstrap.py` is on `CONTRIBUTOR_NEVER`, so
   fabric-coordinator writes the bootstrap half. The `store_enroll.py`
   half is for python-dev.
5. **The gate.** `review_status` reads the fleet's users from
   `lineage.json` (rule 9). For python-dev: `tools/fabric/github/` is
   not on `CONTRIBUTOR_NEVER`, but `post_review.py`'s marker text and
   ADR-020 stay fabric-coordinator's.
6. **The arm.** `arm.py` checks the PR's GitHub author against the
   branch login's user (rule 10). For python-dev.
7. **The quota ledger** keyed by the GitHub user, not the host
   (rule 13). This goes to python-dev-02's j74, as a change to its
   contract.

Steps 1 to 4 come before any cut-over. Steps 5 and 6 come before the
second, because the pilot alone can run under today's gate.

## 4. Cut-over

1. **Pilot:** fabric-coordinator's own login (`user`) first, then one
   python-dev. Read back for each: `gh api user` shows the recorded id,
   a push and a PR show the machine user, a marked review counts on the
   gate, an arming merges, and `rate_limit` shows its own pool.
2. Then the rest, one login at a time, each read back the same way, and
   each one's row filled in below.
3. After the last: `GH_TOKEN` and the SSH key pair leave `SHARED_NAMES`.
   The owner revokes the shared OAuth token and removes the shared SSH
   key from their account. Then both orgs turn on their two-factor
   requirement (rule 11). The ADR amendments named in ADR-062 §8 land.

| login | GitHub user | id | in orgs + team | token stored | sync check | cut over |
|---|---|---|---|---|---|---|
| user | | | | | | |
