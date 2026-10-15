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
- **Fleet names**: `store_provision.SHARED_NAMES`, the values every agent gets. Only the
  operator's store holds them; they are put as themselves and applied as today.
- **Holder-only names**: what only holder commands read in place (the Claude-account
  templates and their assignment records, the keys that mint other keys, the backup's
  session). Never granted, never put.
- **Client names**: every other granted name, the operator's own included. Put into an
  agent's store as `client/<client>/<NAME>.gpg`, beside `env/`, never inside it; `<client>`
  a key of `clients.json`, `<NAME>` matching `NAME_RE`.
- **Holders**: the logins `policies/authority.json` lists as fabric-coordinator holders —
  that list, never a login's name (the guards' `fabric-coordinator(-N)?` pattern is not
  this definition) — read as the account's fabric checkout has it at `origin/main`, never
  from the working tree, as ADR-042 rule 2 reads `lineage.json` and the keys.
- **Expected recipients**: each holder's agent key (`identities/keys/<id>.asc`, certified
  by its lineage, ADR-038 rule 2) and the owner's recovery key (`identities/recovery.asc`).

## Commands

Under `fabric-secrets company`, beside `store` and `provision`. Every command prints JSON
rows or names, never a value; a value enters only on stdin.

| Command | Does |
|---|---|
| `company init <client>` | on an empty store whose default branch refuses a force-push and a deletion (read through the API; refused, naming the setting, when it does not): `.gpg-id` with the expected recipients and an empty `grants.json`, as the root commit, signed, pushed. A store that has commits is left alone. |
| `company clone <client>` | a holder's first contact with an existing store: clones it and verifies its whole history from the root (see Signed and verified); refused, naming the commit, on any commit not a holder's. |
| `company recipients <client> [--json]` | expected against actual recipients; exit 0 equal, 3 different. |
| `company reencrypt <client>` | every entry re-encrypted to the expected recipients, one signed commit. The one command that reads a store whose recipients differ; run after a holder change has merged. |
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
trusted base is the store's root commit, which must itself be a holder's, so a holder that
never held the store verifies all of it, and no base is ever taken from a fetch. Each
holder's clone records, in its own git configuration, the last head it verified, and
refuses a fetched head that does not descend from it: a push back to an older signed
head, which signatures alone would pass.

**Backup.** `store backup` includes every company store the running login can read.

## Threat model

The shared `GH_TOKEN` can push to every company store, so any agent can write to one. A
company store's ciphertext is safe against that; what the repository *says* is not.

| Threat | What stops it |
|---|---|
| An agent rewrites `.gpg-id` to add its own key, and a holder's next `set` encrypts to it | No command encrypts to the repository's `.gpg-id`: every write uses the expected recipients computed from `origin/main`, and a store whose `.gpg-id` differs is refused until `reencrypt`. |
| An agent edits `grants.json` to grant itself a client's name | ADR-042's verification with holders as the writers: an unsigned commit, or one signed by any non-holder key — every agent has a valid signing subkey (ADR-057) — refuses the whole operation, naming the commit. |
| A forged entry (encrypted by anyone to the right recipients) replaces a real one | The same verification: no entry is read from a store whose new commits are not all a holder's. |
| An agent pushes the store back to an older holder-signed head (before a `revoke` or a rotation) | The branch refuses a force-push; a holder refuses a head that does not descend from the last it verified. A holder's first `clone` after such a push cannot tell, which is why the branch setting is checked at `init`. |
| A merge adds a holder to `authority.json` | The holder becomes a reader of every company store at the next `reencrypt`. The anchor is the same as ADR-042's lineage: `origin/main`, under the charter-authority guard and the owner's review of `policies/` — a tripwire, not a wall, said here. |
| A holder that is not an agent's parent writes into its store | `company put` refuses that row, naming the parent; ADR-042's verification would refuse the commit on the agent's side anyway, as a security event. |
| A client's credential reaches another client's work | Namespaced names, one file per client, `fabric-secret-run`'s resolution; tested both ways. The login can still read the file: rule 9's limit, said, not hidden. |
| A value leaks into a log, an argument or the conversation | stdin only, rows without values, a test that greps every output and argv of the suite's runs for the fixtures' values. |
| A holder change leaves a retired holder able to read | The change merges; `recipients` then exits 3 on every company store, which is refused for all but `reencrypt` until a holder runs it; a live check records the stores re-encrypted. Old ciphertext in history stays readable by the old key: rotation of the values is the owner's call. |
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
11. A fresh `clone` of a store holding an unsigned or foreign-signed commit anywhere in its
    history: refused; a root commit not a holder's: refused.
12. A fetched head that is an ancestor of the last verified head: refused, nothing applied.
13. `put` by a holder into a login whose parent is another holder: that row refused,
    naming the parent; the other rows written.
14. A fleet name is put as itself; any other granted name of the operator's store lands
    as `client/<operator>/<NAME>.gpg` and in that client's file, never in `secrets.env`.
15. An entry at a path `status` does not recognise is reported by that path.
16. `store rename` moves the login's grants; the old login has none afterwards.
17. Every command but `reencrypt` refuses a store whose recipients differ.

## Lanes

- **python-dev** (its entry merges): the commands, sync, `fabric-secret-run`, backup and
  their tests, under `tools/` and `tests/`.
- **fabric-coordinator** supplies, as commits onto python-dev's branch before it opens:
  the `operator` field of `projects/clients.json` and its lint; the `description` there,
  which still speaks of a role key; and the branch setting on each company store.
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
a dummy name — init, set, grant, put into one agent, sync, `fabric-secret-run` in and out
of the client's working copy — is written to `docs/live-checks/`; ADR-038 §8 says built.
