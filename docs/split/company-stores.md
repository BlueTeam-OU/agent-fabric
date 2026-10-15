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
| `company clone <client>` | a holder's first contact with an existing store: clones it and reads it as every reader does (see Signed and verified), recording its last verified head. |
| `company recipients <client> [--json]` | expected against actual recipients; exit 0 equal, 3 different. |
| `company reencrypt <client>` | every entry re-encrypted to the expected recipients, one signed commit, a checkpoint; it prints the commit. Run after each holder change merges, by a holder that is still a recipient. An addition: an existing holder runs it, then the added holder `clone`s (starting from that checkpoint) and runs it too. A removal merges only when the store's head is a checkpoint signed by a holder that remains, named in the removal's pull request, and only after the owner has revoked the removed holder's Proton Drive session if it ran `store backup`; a remaining holder runs it again after the merge. |
| `company repair <client>` | a holder, on a store whose read stopped at a commit that does not verify: pushes on top of the head a checkpoint with the tree of P, the last commit its own read verified (so a newer signed `revoke` or rotation its read reached is kept). Readers start from it and never read what lies between P and it. Refused when the holder's own read has no start. |
| `company recover <client>` | the owner, in a terminal, when no holder can read the store (no current holder can decrypt it, or no reader has a start): restores the head of a `store backup` bundle the owner picks by its Proton Drive revision and date, checked against the backup's sha256 manifest (`store backup --verify`) — which proves the transfer, not the origin: the bundle is trusted because only the backing-up login and the owner write that folder — so nothing in the store's own history chooses it. Before it writes, it lists every commit between the bundle's head and the store's head (date, signer, names changed, never a value): these are lost, and the owner re-applies any `revoke` or rotation among them. Pushes on top of the head a checkpoint with that tree, re-encrypted with the recovery key (its passphrase asked by gpg) to the expected recipients, signed by a current holder's key the owner names, with the bundle's sha256 in an `Owner-Recovery:` trailer. Refuses inside a model session (`CLAUDECODE` set), as `paper` does (ADR-038 rule 6). |
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
holders as its only writers in place of rule 2's agent and parent: every commit is signed
by a holder's signing subkey, and a refusal is a security event that `fabric-secrets
status` says. Writers change over time, so each commit records, in a trailer, the
agent-fabric commit whose holders it was written under, and the store it belongs to
(`Company-Store: <owner>/<repo>`, the client's `secrets_store`); both trailers are inside
the signed commit, and a reader treats a commit naming another store as one that does not
verify, so a checkpoint carried over from another client's store is neither a start nor
read. A checkpoint (`init`,
`reencrypt`, `repair`, `recover`) holds the whole store. Every reader — a first `clone`,
a later fetch, `put`, `names`, `repair` — first fetches the fabric's `origin/main`, then:

A store's history is linear: a commit with more than one parent never verifies, and is
never a start.

1. **Start.** Over every commit reachable from the head, through all parents (so a merge
   cannot hide a newer checkpoint), the newest — in topological order, never by commit
   date — checkpoint of this store signed by a holder on
   `origin/main` now, whose signer
   was a holder at the fabric commit it records, which is on `origin/main`; for a reader
   with a last verified head, only one that descends from that head, else that head
   itself. Nothing before the start is read or judged. This is the company store's own
   base, departing from ADR-042 rule 4 (a base set once, never from a fetch): a company
   store has no enrolment bundle, and its start is anchored by a current holder's
   signature, not by the fetch alone. A retired
   holder's checkpoint is never a start, and a fresh reader with no start is refused,
   naming `company recover`.
2. **Forward.** Each commit after the start verifies when its signer is a holder now, was
   one at the fabric commit it records, and that fabric commit is on `origin/main` and no
   older than its parent's. The first that does not verify stops the read: the store is
   refused, naming it, for all but `recipients`, `repair` and `recover`, and P is the last
   commit read.
3. **No rollback.** The reader records its last verified head in its own git
   configuration and refuses a fetched head that does not descend from it.

A repair or a recovery is therefore an ordinary checkpoint: readers start from it and
never read what it covers, so neither needs an exception to ADR-042 rule 3; rule 4's base
is replaced as rule 1 says. A removed
holder's key extends nothing, since every commit after a start must be a current
holder's; what a removed holder signed after the head checkpoint its removal waited for
is lost, and said.

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
| An agent pushes one or more commits that do not verify, which the branch keeps (no force-push), possibly rewriting `.gpg-id` or `grants.json` | Every reader stops at the first, a security event, until a holder runs `repair`: a checkpoint with P's tree on top, which every reader starts from, so nothing after P is read. When no holder can read the store, `recover`. |
| A holder repairs to an older P than another holder's read reaches | Every reader fetches the fabric first, starts over all parents and refuses a merge commit, so holders on the same `origin/main` reach the same P whether fresh or not; a holder that chose an older P on purpose could sign a revert anyway, which adds no capability. |
| An agent pushes a merge commit whose first parent is an older checkpoint, to make a fresh reader start before a newer one | A merge never verifies, and the start is chosen over all parents: the newer checkpoint is found, and the read stops at the merge. |
| A retired holder's key, stolen, signs a commit or a checkpoint | A retired holder's checkpoint is never a start, and every commit after a start must be a current holder's: it is never read. Because of that, a removal merges only when the head is a remaining holder's checkpoint, so nothing the removed holder signed before it is lost. |
| A merge adds a holder to `authority.json` | The holder becomes a reader of every company store at the next `reencrypt`. The anchor is the same as ADR-042's lineage: `origin/main`, under the charter-authority guard and the owner's review of `policies/` — a tripwire, not a wall, said here. |
| A holder that is not an agent's parent writes into its store | `company put` refuses that row, naming the parent; ADR-042's verification would refuse the commit on the agent's side anyway, as a security event. |
| A client's credential reaches another client's work | Namespaced names, one file per client, `fabric-secret-run`'s resolution; tested both ways. The login can still read the file: rule 9's limit, said, not hidden. |
| A value leaks into a log, an argument or the conversation | stdin only, rows without values, a test that greps every output and argv of the suite's runs for the fixtures' values. |
| A holder change leaves a retired holder able to read | The removal merges after the addition; `recipients` then exits 3 on every company store, which is refused for all but `recipients`, `clone`, `reencrypt`, `repair` and `recover` until a remaining holder re-encrypts it; a live check records the stores re-encrypted. Old ciphertext in history stays readable by the old key: rotation of the values is the owner's call. |
| The only holder's key is lost, or every checkpoint's signer has retired | `company recover`, the owner's, in a terminal, from a backup bundle the owner identifies by its Proton revision and date (the manifest proves the transfer only): nothing in the store's history chooses what is restored, and what came after the bundle is listed as lost. The backup folder is written by the backing-up login and the owner alone; a removed holder that backed up has its Proton Drive session revoked by the owner before the removal merges (the `reencrypt` row), so its key, stolen later, opens no session that writes a bundle. A holder whose key is replaced (rule 4) re-encrypts with the new key before the old is revoked, or its old checkpoints stop being starts. |
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
11. A fresh `clone` with an unsigned or foreign-signed commit after its start: refused at
    that commit. A store whose root was signed by a holder since removed, with a later
    checkpoint by a remaining holder: a new holder's `clone` starts there. A commit
    recording an older fabric commit than its parent's: refused. A checkpoint at the head
    signed by a removed holder: never a start, and refused after one.
12. A fetched head that is not a descendant of the last verified head: refused, nothing
    applied.
13. `put` by a holder into a login whose parent is another holder: that row refused,
    naming the parent; the other rows written.
14. A fleet name is put as itself; any other granted name of the operator's store lands
    as `client/<operator>/<NAME>.gpg` and in that client's file, never in `secrets.env`.
15. An entry at a path `status` does not recognise is reported by that path.
16. `store rename` moves the login's grants; the old login has none afterwards.
17. Every command but `recipients`, `clone`, `reencrypt`, `repair` and `recover` refuses a
    store whose recipients differ.
18. After a removal merged with no remaining holder a recipient, `reencrypt` refuses
    naming `company recover`; `recover` refuses with `CLAUDECODE` set.
19. `set` on a store whose branch setting is not read back: refused, naming it.
20. Each writing command, with the branch setting lifted after `init`: refused, naming
    it.
21. The addition order (existing holder `reencrypt`, added holder `clone` and
    `reencrypt`), then the removal: the remaining holder reads the store, and a fresh
    clone by a third holder starts from the remaining holder's checkpoint.
22. Two unsigned commits at the head, the second adding a key to `.gpg-id`, then a
    holder's `repair`: an existing clone and a fresh one both start from the repair,
    neither reads the commits it covers, and `.gpg-id` is P's.
23. Holders A and C; C last verified V_old; A pushes a signed `revoke` V_new; an agent
    pushes X; C runs `repair`: P is V_new, the revoke stands, the next `put` does not
    re-grant.
24. A one-commit attack on a holder's last verified head H: `repair` takes P = H.
25. Holders X, Y, W; X `set`s after Y's checkpoint; the removal of X merges only after
    Y's checkpoint at the head; a lagging W starts from that checkpoint, never reads X's
    commit, and keeps Y's later rotation.
26. In the window after X's removal merges, a commit signed with X's fixture key, recording
    a pre-removal fabric commit: refused by an existing clone and a fresh one.
27. Every checkpoint's signer retired: `recover` restores the bundle the owner picks; a
    bundle whose sha256 differs from the manifest is refused; an existing clone and a
    fresh one both start from the recovery; a commit signed with a retired fixture key,
    newest-dated, is never offered and never read.
28. A holder whose fabric checkout is stale: every reader fetches it first, and P matches
    the one a current holder computes.
29. An unsigned merge whose first parent is an older checkpoint and second the head (after
    a signed `revoke`): a fresh clone's `repair` and an existing holder's `repair` take
    the same P, and the revoke stands.
30. `recover` lists the commits after the bundle's head by name, never a value, before it
    writes; a revoke among them is listed.
31. A merge whose side parent is another fixture client's newer checkpoint, pushed to this
    store: a fresh and an existing reader take the same P, neither starts from the other
    store's checkpoint, and `repair` keeps this store's tree.
32. A single-parent commit signed by a current holder but naming another store in
    `Company-Store:`: refused.

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
of the client's working copy — is written to `docs/live-checks/`, and the first holder
removal records there the Proton Drive session it revoked; ADR-038 §8 says built.
