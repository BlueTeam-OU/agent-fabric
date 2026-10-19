---
name: repo-lifecycle
description: "Move, rename or import a managed repository: ordered checklists of who does each step and why the order matters. Load it whenever the owner says a repository moves, is transferred, renamed, imported or made a managed project; before editing projects/registry.json, projects/clients.json or policies/auto-mode.json for a repository's name; when a clone's origin or a push names a renamed repository (HTTP 307 on a write); and when fabric-pr arm refuses naming a client's settings repository."
---

# Moving and importing a repository

Two procedures, each an ordered checklist. Four lanes do the work; name the
lane before you act, because a step in another lane is a request over GZCoord
(`gzcoord-send` skill), not something to do yourself. The order is the
substance: each step is placed so that nothing in between arms, merges or
resolves wrongly.

| lane | does |
|---|---|
| owner's hand | GitHub transfer, rename, create; GitHub settings and secrets the session cannot change; any `!` command |
| fabric-coordinator | `projects/registry.json`, `projects/clients.json`, `projects/<id>/integration/`, `policies/auto-mode.json`, the tests that name them, the project's `.agent-fabric/` |
| devex-tooling | the client's settings repository (`repos/<repo>.json`), `fabric-repo-policy`, CI wiring and rulesets |
| the project's agents | their own clones: origin and `GH_REPO` |

**Not automated.** No command performs a move or an import end to end.
`fabric-repo-policy` has `plan` and `verify` only; there is no `apply`
verb yet, so applying an arming policy to GitHub is by hand. The settings
repository's validator runs in that repository's CI, not in this tree.

## A. Moving a repository (another organisation, or a rename)

Why this order: `fabric-pr arm` finds a repository's policy through the
registry (project, then client, then the client's `settings_repo`); the
settings repository's validator accepts `repos/<repo>.json` only once the
pinned registry names that client; and old names must keep resolving until
every clone is re-pointed. So the registry lands first, the new settings
file second, the old file last. Between registry and file, arms fail
closed (the fleet default is read, GitHub has no `fabric arming policy`
ruleset, the arm refuses on drift).

1. **Owner:** give fabric-coordinator the old and new `<owner>/<repo>` and
   whether the client changes. The transfer or rename itself (step 8) may
   happen before or after the registry PR; nothing below depends on that,
   only on its being done before step 9.
2. **fabric-coordinator**, `projects/registry.json`, one PR:
   - `remotes`: new ssh then https remotes first (`new_agent.py` takes the
     first `git@`, `results.py` the first GitHub one), the old two kept
     after them so an old clone still resolves to the project.
   - `moved_from`: the old ssh and https remotes. `repoint` in
     `tools/fabric/bootstrap.py` rewrites an origin naming one of them to
     the first current remote of the same scheme, on each account's next
     bootstrap. Each must also be in `remotes` (asserted by
     `tests/test_workingcopy.py`).
   - `client`, when the organisation changes.
   - the `note`: one line saying the project moved.
3. **fabric-coordinator**, same PR, `projects/clients.json`: the new client
   has `settings_repo` (lint refuses a client with projects and none),
   `secrets_store` and `channel`. If the project's work used a credential
   from the old client's store, ask the owner; the store changes with the
   client.
4. **fabric-coordinator**, same PR, `policies/auto-mode.json`: in `Repository
   visibility` and the secrets `hard_deny` sentence, the new name; in
   `Source control`, the old name as "the older name GitHub redirects to
   <new>". Unmoved clones keep pushing through the old name, and a
   classifier that does not know it blocks them. Update the sentence
   `tests/test_auto_mode_policy.py` quotes.
5. **fabric-coordinator**, same PR, `tests/test_workingcopy.py`
   (`test_blueteam_projects_resolve_under_both_github_orgs`): add the
   project, so both names are proved to resolve to it. Run both tests.
6. **Merge the registry PR first.** Tell the project's agents that arms
   refuse until step 7 lands, and why (fail closed, correct).
7. **devex-tooling:** one PR per settings repository. Each settings
   repository validates against its pinned agent-fabric commit
   (`AGENT_FABRIC_REF` in its `.github/workflows/validate.yml`; its
   `tools/validate_policies.py` reads `projects/registry.json` and
   `clients.json` from that checkout). So the PR sets `AGENT_FABRIC_REF`
   to an agent-fabric main commit at or after the step 6 merge AND adds
   `repos/<repo>.json` (new client) or removes it (old client); either
   alone fails CI. Same client, renamed repository: rename the file.
   **Nobody applies the policy by hand until the file has landed**: an
   apply under the fleet default would replace the queue, required checks
   and rulesets with the default.
8. **Owner:** transfer or rename on GitHub, then what a transfer does not
   carry: Actions secrets and variables, deploy keys, apps, webhooks,
   team access. Rulesets, branch protection and workflows travel with it.
9. **devex-tooling:** `fabric-repo-policy verify <new owner/repo>` exits 0
   (1 is drift, 2 unreadable); `fabric-repo-policy plan <owner/repo>` says
   "no change" or what differs. Confirm CI runs under the new name.
10. **fabric-coordinator:** find what still names the old repository,
    `grep -rn "<old owner>/<repo>" projects/ policies/ docs/ communication/`
    and in the working copy's `.agent-fabric/` and CLAUDE.md. Fix
    `projects/<id>/integration/`; the project's own files go by a PR there
    (the `.agent-fabric/` fence). `fabric-ref` stays: only a drain moves
    it (ADR-011). `communication/` protocol examples are a normative
    contract (ADR-032): changing one is an amendment, queue it.
11. **fabric-coordinator:** `fabric-ctl all upgrade fabric`, so every
    account's bootstrap runs `repoint`; read back with `fabric-ctl all status`.
12. **The project's agents**, until their clone is re-pointed: API writes
    through the old name fail with HTTP 307, fetch and read still work.
    `export GH_REPO=<new owner>/<repo>` and `git remote set-url origin
    <new remote>` (same scheme as the old one) fix it by hand.
13. **fabric-coordinator:** broadcast to the project's agents: the new
    name, steps 6 and 12. Read back in `fabric-history` that it was sent.

Lessons: a registry-only move left old clones unable to write (hence
`moved_from`); a registry change without its settings file puts the
repository on the fleet default (hence steps 6 and 7); an auto-mode
policy that dropped the old name blocked unmoved clones (step 4). Compare
earlier moves with `grep -n moved_from projects/registry.json`.

## B. Importing a repository (making it a managed project)

Why this order: the registry entry is what makes a working copy a project
and names its client; the client's settings repository must hold the
arming policy before anything arms there; and the project's CI pins the
fabric by `fabric-ref`, so the project's files exist before its CI runs.

1. **Owner:** say which repository, which client (an existing entry in
   `projects/clients.json`; a new client is a decision of its own), which
   roles work there and its visibility; create or transfer it on GitHub.
   Steps 2 to 4 start from one command, `git fetch` first:
   `<checkout>/bin/fabric-project import --id ID --like SIBLING --client
   CLIENT --remote SSH --remote HTTPS --default-branch B --license SPDX
   --role ROLE … --title T --working-copy <the project's clone>`. It
   edits the agent-fabric checkout its own `bin/` sits in, never the
   directory you stand in, so run it by the path of your branch's
   checkout: the linked `fabric-project` writes into the checkout
   bootstrap linked. Without `--working-copy` it writes no step 4 file
   and says nothing of it. It prints the plan; `--write` writes the
   files (never commits, never overwrites). What it leaves to you is in
   each step below and in the lines it lists as still naming the
   sibling.
2. **fabric-coordinator**, `projects/registry.json`, one new entry
   (the import takes the sibling's keys in its order; `title` is the
   sibling's unless `--title`; `tools` empty, and `agent_env` and
   `plain_env` too where the sibling has them; `note` is `imported
   <date>`; `moved_from` never copied):
   `client`, `title`, `remotes` (ssh then https),
   `default_branch`, `taxonomy` (`.agent-fabric/taxonomy.json`), `memory`
   (`.agent-fabric/memory`), `integration` (`projects/<id>/integration`),
   `license`, `tools` (each with `proof`, `where`, `why`; `roles` to limit
   it; an `install` block with a pinned `sha256` for what an account
   fetches), `agent_env`/`plain_env` for variables, a `note`. Check the
   tools with `bin/fabric-tools` in the working copy. Lint refuses a
   project id named in a generic file, so the name stays under
   `projects/<id>/`.
3. **fabric-coordinator**, `projects/<id>/integration/`: compare two
   projects (`find projects/<a> projects/<b> -type f`). Typical:
   `gh/arm.json` (`boundary.paths`, `exempt`, `waiver_role`, the commit
   floor and its reasons), `gh/guards.json`, `gh/collisions.json`,
   `gzcoord/config.json`, `gzcoord/CLAUDE.snippet.md`, `gzcoord/CLAUDE.md`.
   `gh/compliance.json`, `gh/trial.json` and `pr-tools.json` exist only
   where the project uses those `fabric-pr` verbs (`--with-compliance`,
   `--with-trial`, `--with-pr-tools`). The import copies the sibling's
   files with its id replaced, values included: `boundary.paths`,
   `exempt`, `waiver_role`, the commit floor and its reasons, and the
   prose are checked by hand against the new project.
4. **fabric-coordinator**, in the project's working copy, by a PR there
   (only fabric-coordinator commits under `.agent-fabric/`):
   `taxonomy.json` (shape: `projects/schemas/taxonomy.schema.json`),
   `roles/<role>.md` remits for the roles that work there (the import
   copies the sibling's, from `--like-working-copy` or the sibling's
   clone beside the checkout; it writes a stub for a role that clone
   lacks, and for every role when no clone is found, which only the
   sizes in the plan show; charters are never copied), `memory/` (a
   drain fills it), `fabric-ref` (one line, a full commit id of this
   repository, ADR-011; the import writes origin/main as last fetched).
   The import writes the taxonomy with an empty rule per role, to be
   filled.
5. **devex-tooling:** one PR in the client's `settings_repo`. It validates
   against its pinned agent-fabric commit (`AGENT_FABRIC_REF` in
   `.github/workflows/validate.yml`; `tools/validate_policies.py` reads
   `projects/registry.json` and `clients.json` from that checkout). So the
   PR sets `AGENT_FABRIC_REF` to an agent-fabric main commit at or after
   the step 2 merge AND adds `repos/<repo>.json`; either alone fails CI. Then `fabric-repo-policy plan
   <owner/repo>`; apply by hand only when the file is on the settings
   repository's default branch.
6. **fabric-coordinator**, `policies/auto-mode.json`: name the repository
   under PUBLIC, INTERNAL or PRIVATE in `Repository visibility` (an
   unnamed repository is outside the trust boundary), and in `Source
   control` where main protection is described; keep
   `tests/test_auto_mode_policy.py` in step.
7. **devex-tooling:** the project's CI: a workflow that checks out this
   repository at the `fabric-ref` commit and runs the fabric's guards and
   corpus lint (ADR-011), actions pinned by sha
   (`policies/check_actions_pinned_by_sha.py`), the policy's
   `required_checks` matching the job names.
8. **Roles:** each role that works there has its remit (step 4); a
   contributor role also needs an entry in `policies/authority.json`
   (fabric-coordinator's PR). After `fabric-ctl all upgrade fabric`,
   bootstrap installs the hooks in the registered working copy.
9. **Read-back, fabric-coordinator:** `python3 tools/fabric/lint.py
   --no-siblings`; `fabric-adr lookup <topic>` for each decision the
   project touches; `fabric-repo-policy verify <owner/repo>`; the first
   `fabric-pr arm` reads the project's file (a missing file is no error: a
   404 falls to the fleet policy, a drift refusal or a plan against the
   fleet ruleset, so step 5 not landed shows there; an error naming the
   settings repository means the client or its `settings_repo` is wrong or
   unreadable). Then message the
   roles that work there.

Not automated yet: the CI workflow, and applying the arming policy to
GitHub. The entry, the integration directory and the `.agent-fabric/`
files are scaffolded by `fabric-project import` and finished by hand.
