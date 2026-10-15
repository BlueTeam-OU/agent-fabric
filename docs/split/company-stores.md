# Company stores — the tooling contract (ADR-038 rule 10)

What the tooling for a company's store must do, refuse and prove. The decision is
agent-fabric ADR-038 rule 10 (A 2026-10-15); which client a working copy belongs to is
ADR-045 rule 5; which names move into which store is
[company-store-names.md](company-store-names.md), the owner's review. This file is the
acceptance a contributor builds to, and it is engine: it names no company.

## Terms

- **Company store**: the private repository a client's `secrets_store` names in
  `projects/clients.json`. The same pass(1) layout as an agent's store: `.gpg-id`,
  `env/<NAME>.gpg` with the value on the first line, plus one plain file, `grants.json`.
- **The operator's client**: the client that is the company running the agents.
  `projects/clients.json` names it in a top-level `operator` field (supplied by
  fabric-coordinator with its lint; see Lanes).
- **Fleet names**: `store_provision.SHARED_NAMES`, the values every agent gets, held only
  by the operator's store; and the values a holder command derives for every agent as it
  does today (`assign`'s `CLAUDE_CODE_OAUTH_TOKEN`, `codex-token`'s `CODEX_CHATGPT_*`).
  Put as themselves and applied as today.
- **Holder-only names**: what only holder commands read in place (the Claude-account
  templates and their assignment records, the keys that mint other keys, the backup's
  session). Never granted, never put; a command may put what it derives from one, as a
  fleet name.
- **Client names**: every other granted name, the operator's own included. Put into an
  agent's store as `client/<client>/<NAME>.gpg`, beside `env/`, never inside it; `<client>`
  a key of `clients.json`, `<NAME>` matching `NAME_RE`.
- **Holders**: the logins `policies/authority.json` lists as fabric-coordinator holders —
  that list, never a login's name (the guards' `fabric-coordinator(-N)?` pattern is not
  this definition). The holders *now* are read as the account's fabric checkout has
  `origin/main`, never the working tree, as ADR-042 rule 2 reads `lineage.json` and the
  keys; the holders *of a commit* are read at the fabric commit it records (Signed and
  verified).
- **Expected recipients**: each holder's agent key (`identities/keys/<id>.asc`, certified
  by its lineage, ADR-038 rule 2) and the owner's recovery key (`identities/recovery.asc`).

## Commands

Under `fabric-secrets company`, beside `store` and `provision`. Every command prints JSON
rows or names, never a value; a value enters only on stdin.

| Command | Does |
|---|---|
| `company init <client>` | on an empty store: `.gpg-id` with the expected recipients and an empty `grants.json`, as the root commit and first checkpoint, signed, pushed. A store that has commits is left alone. Every writing command after it (`set`, `rm`, `import`, `grant`, `revoke`, `reencrypt`, `repair`, `recover`, the rename's grant rewrite) first reads back (through the API) that the default branch refuses a force-push and a deletion, and refuses, naming the setting, when it does not. |
| `company clone <client>` | a holder's first contact with an existing store: clones it and verifies it from the newest checkpoint its own login can anchor (see Signed and verified), as far as commits verify; it records that commit as its last verified head and names the first that does not verify, after which the store is refused for all but `repair` and `recover`. |
| `company recipients <client> [--json]` | expected against actual recipients; exit 0 equal, 3 different. |
| `company reencrypt <client>` | every entry re-encrypted to the expected recipients, one signed commit, a checkpoint. Run after each holder change merges, by a holder that is still a recipient. After an addition the added holder runs it (its `clone` starts from an existing holder's checkpoint, and it can decrypt once an existing holder's `reencrypt` has run, so the order is: existing holder `reencrypt`, added holder `clone`, added holder `reencrypt`); a removal merges only after the store's newest checkpoint is signed by a holder that remains, and is re-encrypted by a remaining one. |
| `company repair <client>` | a holder, on a store refused for a commit that does not verify. Fetches the fabric's `origin/main` first, so every holder judges the same holders. Verifies forward from its own start (its last verified head, or a fresh clone's checkpoint) along the first-parent chain as far as commits verify; P is the start itself or the last commit after it that verifies. Pushes on top of the head a checkpoint R with P's tree (so P's `.gpg-id` and grants: no newer signed commit is undone), `Supersedes: <P>..<head>` (every commit after P), and a recorded fabric commit judged against P's, never against a superseded one. Refused, naming why, only when its start cannot be anchored. Exempt from the recipients rule, which it judges at P. |
| `company recover <client>` | the owner, in a terminal, when no remaining holder can decrypt, or none can anchor a start (every checkpoint's signer retired): pushes a repair checkpoint as `repair` does when a commit does not verify, P from the newest checkpoint any current holder signed; when there is none, P is a commit the owner names after the command lists each candidate's date, signer, recorded fabric commit and entry names, and no forward walk follows it. Then, as a separate checkpoint, re-encrypts with the recovery key (its passphrase asked by gpg) to the holders on `origin/main`, signed by a holder's key that the owner names. Refuses inside a model session (`CLAUDECODE` set), as `paper` does (ADR-038 rule 6). |
| `company set <client> NAME` / `rm <client> NAME` | writes or removes an entry, value on stdin; one signed commit each. |
| `company names <client> [--json]` | the entries, by name, with their grants. |
| `company grant <client> NAME <login…\|all>` / `revoke …` | edits `grants.json` (`{"NAME": ["login", …] \| "all"}`), one signed commit. |
| `company put <client> [--name NAME]… [<login…>] [--replace]` | decrypts each granted name and `put`s it into each granted login's own store: a fleet name as itself, a client name as `client/<client>/<NAME>`; a holder-only name is refused. Only into a login whose recorded parent (`lineage.json`) is the running holder, since ADR-042 rule 2 admits no other writer; any other login's row is refused, naming its parent. With no login, every granted one. Rows as `provision share`'s: written, present, skipped, failed. |
| `company import <client> NAME` | moves an entry of the running holder's own store into the company store, decrypting only inside the process; the own entry is removed only by a separate `store rm`, after the owner's review. |

`provision share` reads the fleet names from the operator's store once it holds them,
from the holder's own store until then. A fleet name the owner retires leaves
`SHARED_NAMES` in the same change, so the allowlist never names a value no store holds.
The holder commands that read holder-only names (`template-set`, `assign`,
`provision issue-key`, `store backup`) read them from the operator's store once it holds
them.

**Sync.** An agent's `client/<client>/<NAME>.gpg` entries go to
`~/.config/agent-fabric/clients/<client>.env` (0600, one file per client), never to
`secrets.env` or `env.sh`; a file for a client the store no longer holds is removed.
`fabric-secrets status` reports each client's names, never values, and reports by path
any entry it does not recognise — a sync that does not know `client/` must not drop one
silently, so this lands before the first `put`.

**Use.** `fabric-secret-run` adds a client's file to the command's environment only when
the working copy resolves to that client (`workingcopy.resolve_client`); elsewhere it
refuses a client-namespaced name by name. The SessionStart scrub (ADR-038 rule 9) covers
the client files too.

**Signed and verified.** ADR-042 holds for a company store as for an agent's, with the
holders as its only writers in place of rule 2's agent and parent: every commit signed by
a holder's signing subkey, every fetch, `put` and `names` verifying each commit beyond the
trusted base, and a refusal a security event that `fabric-secrets status` says. The
writers change over time, so each commit records, in a trailer, the agent-fabric commit
whose holders it was written under; it verifies when that fabric commit is on
`origin/main`, is not older than the one its parent records, and its signer was a holder
there and is one on `origin/main` now: a removed holder's commit never verifies after a
start, whatever fabric commit it records, so a stolen retired key extends nothing. A
re-encryption is a checkpoint. A holder that never held the store verifies from
the newest checkpoint whose signer is a holder on `origin/main` now and was one at the
fabric commit it records, which is no older than the one its parent records (for a repair
checkpoint, P's, here and in the rule above), forward to
the head, each commit after it verified as above — history before it is not judged, as
ADR-042's base, and no base is ever taken from a fetch alone. A checkpoint signed by a
retired holder is never a starting point; one after the start is refused. Each holder's clone records,
in its own git configuration, the last head it verified, and refuses a fetched head that
does not descend from it: a push back to an older signed head, which signatures alone
would pass. A repair checkpoint (`repair`) is read and the commits it supersedes are not:
it verifies when it is signed by a holder now, its tree is exactly its named P's, P
verifies, and every commit between P and it is named; then verification continues after
it.

**Backup.** `store backup` includes every company store the running login can read.

## Threat model

The shared `GH_TOKEN` can push to every company store, so any agent can write to one. A
company store's ciphertext is safe against that; what the repository *says* is not.

| Threat | What stops it |
|---|---|
| An agent rewrites `.gpg-id` to add its own key, and a holder's next `set` encrypts to it | No command encrypts to the repository's `.gpg-id`: every write uses the expected recipients computed from `origin/main`, and a store whose `.gpg-id` differs is refused for all but `recipients`, `clone`, `reencrypt`, `repair` and `recover` until a re-encryption, repair or recovery leaves it matching. |
| An agent edits `grants.json` to grant itself a client's name | ADR-042's verification with holders as the writers: an unsigned commit, or one signed by any non-holder key — every agent has a valid signing subkey (ADR-057) — refuses the whole operation, naming the commit. |
| A forged entry (encrypted by anyone to the right recipients) replaces a real one | The same verification: no entry is read from a store whose new commits are not all a holder's. |
| An agent pushes the store back to an older holder-signed head (before a `revoke` or a rotation) | The branch refuses a force-push; a holder refuses a head that does not descend from the last it verified. A holder's first `clone` after such a push cannot tell, which is why no entry is written before the branch setting is read back, and why the live check records that the fleet `GH_TOKEN` cannot lift it. |
| An agent pushes one or more commits that do not verify, which the branch keeps (no force-push), possibly rewriting `.gpg-id` or `grants.json` | Every holder refuses the store, a security event, until a holder runs `repair`: P's tree — the last commit that verifies, so a newer signed `revoke` or rotation is kept — over the head, superseding everything after P. A repair is a start for a fresh clone like any other; an existing clone reads it and not what it supersedes. When no holder can, `recover`. |
| A holder repairs to an older P than the last that verifies | Not checked by verifiers: a holder can sign a reverting commit anyway, so this adds no capability; `repair` computes P itself, and its rows say which P. |
| A retired holder's key, stolen, signs a new commit or a forged checkpoint at the head | A commit verifies after a start only when its signer is a holder now, so it does not verify, even in the window between the removal merging and a remaining holder's checkpoint; and a fresh clone never starts from a checkpoint whose signer is not a holder now. Commits a removed holder signed and no remaining holder verified before the removal are lost to a repair, which is why the removal waits for a remaining holder's checkpoint. |
| A merge adds a holder to `authority.json` | The holder becomes a reader of every company store at the next `reencrypt`. The anchor is the same as ADR-042's lineage: `origin/main`, under the charter-authority guard and the owner's review of `policies/` — a tripwire, not a wall, said here. |
| A holder that is not an agent's parent writes into its store | `company put` refuses that row, naming the parent; ADR-042's verification would refuse the commit on the agent's side anyway, as a security event. |
| A client's credential reaches another client's work | Namespaced names, one file per client, `fabric-secret-run`'s resolution; tested both ways. The login can still read the file: rule 9's limit, said, not hidden. |
| A value leaks into a log, an argument or the conversation | stdin only, rows without values, a test that greps every output and argv of the suite's runs for the fixtures' values. |
| A holder change leaves a retired holder able to read | The removal merges after the addition; `recipients` then exits 3 on every company store, which is refused for all but `recipients`, `clone`, `reencrypt`, `repair` and `recover` until a remaining holder re-encrypts it; a live check records the stores re-encrypted. Old ciphertext in history stays readable by the old key: rotation of the values is the owner's call. |
| The only holder's key is lost | `company recover`, the owner's, in a terminal. |
| A holder change leaves agents whose lineage parent is no longer a holder | `put` refuses every such row (ADR-042 rule 2). The holder that is every agent's parent is not removed until lineage can re-parent its children, a change of ADR-039's of its own. |
| A non-holder runs a writing command | Refused before any decryption: the running login must be a holder at `origin/main`. |
| A login renamed (`store rename`) keeps or loses a grant | Grants are rewritten by the rename, in a holder's signed commit, before the old login can be reused; tested. |

## Refusal tests (the acceptance)

Each in the suite, with a throwaway `GNUPGHOME`, fixture keys and a local bare repository
as the company store; the suite passes with `AGENT_FABRIC_OPERATOR` unset and set
(ADR-045 rule 3).

1. `set` after `.gpg-id` gained a key: refused, nothing written, exit 3.
2. `put` after a commit to `grants.json` that is unsigned, and again after one signed by a
   non-holder fixture agent's key: refused both times, naming the commit, no store written.
3. `put` of a name to a login not in its grants: refused for that row only.
4. A writing command by a non-holder login: refused before gpg is called.
5. A client name never lands in `secrets.env`; it lands in its client's file, 0600.
6. `fabric-secret-run` in a working copy of client A refuses a name of client B, and
   gives client A's name.
7. `reencrypt` after a holder change: every entry readable by the new holder, not by the
   removed one, and `recipients` exits 0.
8. No fixture value appears in any command's stdout, stderr or argv.
9. `import` leaves the holder's own entry in place.
10. An entry replaced by a commit signed with a non-holder fixture key: `names`, `put` and
    the fetch each refuse, naming the commit.
11. A fresh `clone` of a store holding, after its newest anchorable checkpoint, an
    unsigned or foreign-signed commit: refused. A store whose root was signed by a holder
    since removed, re-encrypted at a checkpoint by a remaining holder: a new holder's
    `clone` succeeds. A commit recording an older fabric commit than its parent's:
    refused. A checkpoint at the head signed by a removed holder, recording an older
    fabric commit: a fresh `clone` neither starts from it nor accepts it.
12. A fetched head that is an ancestor of the last verified head: refused, nothing applied.
13. `put` by a holder into a login whose parent is another holder: that row refused,
    naming the parent; the other rows written.
14. A fleet name is put as itself; any other granted name of the operator's store lands
    as `client/<operator>/<NAME>.gpg` and in that client's file, never in `secrets.env`.
15. An entry at a path `status` does not recognise is reported by that path.
16. `store rename` moves the login's grants; the old login has none afterwards.
17. Every command but `recipients`, `clone`, `reencrypt`, `repair` and `recover` refuses a
    store whose recipients differ.
18. After a removal merged alone (no remaining holder is a recipient), `reencrypt` refuses
    naming `company recover`; `recover` refuses with `CLAUDECODE` set.
19. `set` on a store whose branch setting is not read back: refused, naming it.
20. Each writing command, with the branch setting lifted after `init`: refused, naming
    it.
21. A removal merged while the newest checkpoint is the removed holder's: the remaining
    holder's `clone` refuses, naming the order and `company recover`; with the added
    holder's own `reencrypt` before the removal, its `clone` succeeds afterwards.
22. Two unsigned commits at the head, the second adding a key to `.gpg-id`, then a
    holder's `repair`: an existing clone and a fresh one both accept the store, neither
    reads the superseded commits' entries, and `.gpg-id` is P's. A repair signed by a
    non-holder, one whose tree differs from P's, and one that leaves a commit after P
    unnamed: each refused.
23. Holders A and C; C last verified V_old; A pushes a signed `revoke` V_new; an agent
    pushes X; C runs `repair`: P is V_new, the revoke stands, and the next `put` does not
    re-grant.
24. A superseded commit recording the newest fabric commit does not make the repair fail
    its fabric-commit check, which is judged against P's.
25. No holder with a verified head and a head that does not verify: a holder's `repair`
    from a fresh-clone start succeeds. Every checkpoint's signer retired and no holder a
    recipient: `recover` takes the P the owner names, pushes a repair checkpoint, then a
    re-encryption; an existing clone and a fresh one both accept the store. A commit
    signed with the removed holder's fixture key after that P is never taken.
29. In the window after a removal merges and before a remaining holder's checkpoint, a
    commit signed by the removed holder recording the pre-removal fabric commit: refused
    by an existing clone.
26. A one-commit attack on a holder's last verified head H: `repair` takes P = H.
27. A fresh clone whose newest checkpoint is a repair whose superseded commit records a
    newer fabric commit than the repair: the clone starts from the repair.
28. A holder whose fabric checkout is stale: `repair` fetches it first, and P matches the
    one a current holder computes.

## Lanes

- **python-dev** (its entry merges): the commands, sync, `fabric-secret-run`, backup and
  their tests, under `tools/` and `tests/`.
- **fabric-coordinator** supplies, as commits onto python-dev's branch before it opens:
  the `operator` field of `projects/clients.json` and its lint, and the branch setting on
  each company store.
- python-dev also owns the store's name handling: `NAME_RE` and `names()` (`core.py`,
  `entries.py`) read only `env/<NAME>.gpg` today; client entries are a second, separate
  reader of `client/<client>/<NAME>.gpg`, and `reserved.py` learns the prefix.
- **The owner**: the names to move ([company-store-names.md](company-store-names.md)) and
  any rotation of values the move exposes.

## Out of scope

Moving any name (after the owner's review, a holder runs `company import`, `grant` and
`put`); the engagement repositories (ADR-045 stage 5); per-client channels; holding
secrets in another account (ADR-038 §7); changing what an agent's own store holds.

## Done when

The refusal tests pass in `tests/run.sh`; one live read-back on the operator's store with
a dummy name — init, the branch setting read back and the fleet `GH_TOKEN` refused when
it tries to lift it, set, grant, put into one agent, sync, `fabric-secret-run` in and out
of the client's working copy — is written to `docs/live-checks/`; ADR-038 §8 says built.
