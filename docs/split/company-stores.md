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
  fabric-coordinator with its lint; see Lanes). Its names are fleet-wide; every other
  client's are namespaced.
- **Holders**: the logins `policies/authority.json` names as fabric-coordinator holders,
  read as the account's fabric checkout has it at `origin/main`, never from the working
  tree — as ADR-042 rule 2 reads `lineage.json` and the keys.
- **Expected recipients**: each holder's agent key (`identities/keys/<id>.asc`, certified
  by its lineage, ADR-038 rule 2) and the owner's recovery key (`identities/recovery.asc`).

## Commands

Under `fabric-secrets company`, beside `store` and `provision`. Every command prints JSON
rows or names, never a value; a value enters only on stdin.

| Command | Does |
|---|---|
| `company init <client>` | clones the client's store, writes `.gpg-id` with the expected recipients and an empty `grants.json`, one signed commit, pushed, and records that commit as the store's trusted base (ADR-042 rule 4). A store that already has commits is left alone. |
| `company recipients <client> [--json]` | expected against actual recipients; exit 0 equal, 3 different. |
| `company reencrypt <client>` | every entry re-encrypted to the expected recipients, one signed commit. The way a holder change reaches a store. |
| `company set <client> NAME` / `rm <client> NAME` | writes or removes an entry, value on stdin; one signed commit each. |
| `company names <client> [--json]` | the entries, by name, with their grants. |
| `company grant <client> NAME <login…\|all>` / `revoke …` | edits `grants.json` (`{"NAME": ["login", …] \| "all"}`), one signed commit. |
| `company put <client> [--name NAME]… [<login…>] [--replace]` | decrypts each name in the company store and `put`s it into each granted login's own store: the operator's names as themselves, another client's as `client/<client>/<NAME>`. With no login, every granted one. Rows as `provision share`'s: written, present, skipped, failed. |
| `company import <client> NAME` | moves an entry of the running holder's own store into the company store, decrypting only inside the process; the own entry is removed only by a separate `store rm`, after the owner's review. |

`provision share` reads its shared names from the operator's company store once it holds
them, from the holder's own store until then; `SHARED_NAMES` stays its allowlist.

**Sync.** An agent's `client/<client>/<NAME>` entries go to
`~/.config/agent-fabric/clients/<client>.env` (0600, one file per client), never to
`secrets.env` or `env.sh`; a file for a client the store no longer holds is removed.
`sync --status` reports each client's names, never values.

**Use.** `fabric-secret-run` adds a client's file to the command's environment only when
the working copy resolves to that client (`workingcopy.resolve_client`); elsewhere it
refuses a client-namespaced name by name. The SessionStart scrub (ADR-038 rule 9) covers
the client files too.

**Signed and verified.** ADR-042 holds for a company store as for an agent's, with the
holders as its only writers in place of rule 2's agent and parent: every commit signed by
a holder's signing subkey, every fetch, `put` and `names` verifying each commit beyond the
trusted base, and a refusal a security event that `fabric-secrets status` says.

**Backup.** `store backup` includes every company store the running login can read.

## Threat model

The shared `GH_TOKEN` can push to every company store, so any agent can write to one. A
company store's ciphertext is safe against that; what the repository *says* is not.

| Threat | What stops it |
|---|---|
| An agent rewrites `.gpg-id` to add its own key, and a holder's next `set` encrypts to it | No command encrypts to the repository's `.gpg-id`: every write uses the expected recipients computed from the trust base, and a store whose `.gpg-id` differs is refused until `reencrypt`. |
| An agent edits `grants.json` to grant itself a client's name | ADR-042's verification with holders as the writers: an unsigned or foreign-signed commit beyond the trusted base refuses the whole operation, naming the commit. |
| A forged entry (encrypted by anyone to the right recipients) replaces a real one | The same verification: no entry is read from a store whose new commits are not all a holder's. |
| A client's credential reaches another client's work | Namespaced names, one file per client, `fabric-secret-run`'s resolution; tested both ways. The login can still read the file: rule 9's limit, said, not hidden. |
| A value leaks into a log, an argument or the conversation | stdin only, rows without values, a test that greps every output and argv of the suite's runs for the fixtures' values. |
| A holder change leaves a retired holder able to read | `recipients` exits 3 on every company store until `reencrypt`; the charter's holder-change commit names the stores re-encrypted. Old ciphertext in history stays readable by the old key: rotation of the values is the owner's call. |
| A non-holder runs a writing command | Refused before any decryption: the running login must be a holder at the trust base. |

## Refusal tests (the acceptance)

Each in the suite, with a throwaway `GNUPGHOME`, fixture keys and a local bare repository
as the company store; the suite passes with `AGENT_FABRIC_OPERATOR` unset and set
(ADR-045 rule 3).

1. `set` after `.gpg-id` gained a key: refused, nothing written, exit 3.
2. `put` after an unsigned commit to `grants.json`: refused, no store written.
3. `put` of a name to a login not in its grants: refused for that row only.
4. A writing command by a non-holder login: refused before gpg is called.
5. A client name never lands in `secrets.env`; it lands in its client's file, 0600.
6. `fabric-secret-run` in a working copy of client A refuses a name of client B, and
   gives client A's name.
7. `reencrypt` after a holder change: every entry readable by the new holder, not by the
   removed one, and `recipients` exits 0.
8. No fixture value appears in any command's stdout, stderr or argv.
9. `import` leaves the holder's own entry in place.

## Lanes

- **python-dev** (its entry merges): the commands, sync, `fabric-secret-run`, backup and
  their tests, under `tools/` and `tests/`.
- **fabric-coordinator** supplies, as commits onto python-dev's branch before it opens:
  the `operator` field of `projects/clients.json` and its lint, and the reserved-name
  rule for `client/` in `tools/fabric/secretstore/reserved.py` if lint must know it.
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
