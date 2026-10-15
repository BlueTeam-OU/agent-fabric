# ADR-038 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-29 — The recovery copy and the backup go to Proton Drive

The owner chose not to print the per-agent sheets: "you will simply
access proton drive via cli and save that there". Each key's recovery
copy, and a bundle of every store, therefore go to a Proton Drive
account dedicated to the fleet. Proton Drive has no app keys, so the
owner's own account never signs in on the agents' host. The trade was
named before it was taken: that account becomes the single recovery
point for every agent, so its 2FA and recovery phrase are what the owner
keeps. It was read back live on the coordinator: a backup, a
`--verify` of that backup against its manifest, and its recovery copy.

### Amendment 2026-09-29 — Recovery copies are encrypted to the owner's recovery key

A Proton session gives full access to the whole account, and an agent's
key can only be exported by that agent. So the plain copy the previous
amendment put in Proton would have made every agent able to read every
other agent's key, once each held a session. The owner chose option B
over the alternatives: every agent holding the fleet's session, or the
owner uploading each copy by hand. Under B, one recovery key protected
by the owner's passphrase receives every copy. Agents encrypt to its
public half and never hold a Proton session, the parent carries the
ciphertext, and only the owner, with the passphrase, can open a copy.
The coordinator's earlier plain copy is replaced, then deleted.

### Amendment 2026-09-29 — Keys and stores are named by the agent id

The owner decided that each agent has an id: a UUIDv7 minted from its
birth (ADR-039). The committed key, the lineage entry and the secrets
repository are now named by that id rather than by the login, so a
renamed login keeps them, and a reused name cannot inherit them. The
coordinator's repository `secrets-user` was renamed on GitHub to
`agent-fabric-secrets-019bbe31-2fff-7a2f-9849-96bdf286e011`, and its key
gained a user id addressed to that id.

### Amendment 2026-09-29 — One identity key per agent, a key per use beneath it

The owner's view: different uses are better served by different keys.
The one key did everything: its primary certified and signed, and its
single subkey opened the store. Now:
- **New keys:** the primary only certifies, and the key carries one
  subkey per use: encryption, signing and authentication.
- **Existing keys** gain the subkeys they lack and keep their
  fingerprints. The coordinator's key gained a signing and an
  authentication subkey. Its primary keeps the signing capability it
  was made with, and gpg signs with the newer subkey.
- **`verify` and lint** refuse a committed key that lacks a use's subkey,
  or whose primary encrypts or authenticates.
- **Formats other than OpenPGP** stay separate keys: the control-plane
  Ed25519 key, and a Radicle node key if one comes.

### Amendment 2026-09-30 — Doppler is removed: every account reads its own store, and a parent fills a child's with provision

Every one of the 16 accounts reads its own store with nothing missing
(docs/live-checks/2026-09-29-fleet-secrets-enrolment.md), and both
Claude-account templates are in the coordinator's store, so the Doppler
code goes, as §7 said it would: `fabric-secrets`' reader and its
`digest --source`, `store import-doppler`, the `secrets-migrate` action,
`enroll.sh` with its worker, the Doppler templates and dual write of
`fabric-accounts`, and `fabric-ctl keygen`'s Doppler branch.
`fabric-secrets sync` moved from a bash heredoc into
`tools/fabric/secrets_sync.py`, since it needed a substantial change and
new tooling is Python.

What `enroll.sh` did for a new account — identity, the shared names,
a key of its own on OpenRouter and OpenAI — is `fabric-secrets
provision`, the parent's `put` into the child's store; `new-agent.sh`
runs it after `store-enroll.sh`, and stops when the parent has no store.
The shared names are an allowlist. Removing the binary and the tokens
from the hosts, and closing the Doppler project, are left in §7.

### Amendment 2026-10-01 — A new account's store reaches it as a bundle

The first account made after the stores replaced Doppler, python-dev-01,
stopped at enrolment: its own push of its new store was refused by
GitHub, because the account had no key — its SSH key is one of the
entries its parent provisions into that store. Every earlier account
already had GitHub access when it was enrolled, and the account-creation
test mocks GitHub, so neither had met it. The owner chose the bundle
path: the store holds only ciphertext, so its history may travel through
the host executor, and the parent pushes and fetches for the child until
its first sync has written its key.

### Amendment 2026-10-06 — No secret in a session's shell

`fabric-secrets sync` wrote `secrets.env` and a `~/.bashrc` line that
sourced it, so every shell, session, Bash call and subagent of an account
held every synced secret. A reviewer printed its environment and the
operator's signing key was rotated (#95); the review guard's clean
environment (ADR-020) then fenced the review class alone. The owner asked
for credential minimisation and approved the plan on 2026-10-06, scoped
to the environment of every session, the harness's own token staying in
its process and unset for Bash.

What was measured first: every reader of the relay token and the search
keys already read the file; `shim.py` and the broker launch needed the
key in the environment; gh needs `GH_TOKEN` or its own configuration;
`GZAPP_PORT_OFFSET` is a plain value a shell needs, hence `plain_env`.
The harness's own `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` was not taken: on
2.1.285 it runs Bash in a bubblewrap sandbox with protected paths, not a
variable filter.

What it does not do is said in the rule: the store's key has no
passphrase, so a session that reads the file reaches the secret. The
step that would close that is §7's broker in another account.

### Amendment 2026-10-07 — The fabric removes only its own Doppler leftover

§6's "Doppler off the hosts" corrected. The owner: "doppler is still used
for secrets inside the gzapp repo". gzapp's local stack loads its
application secrets with `doppler run -- make up` and `make seed-secrets`
(project gzapp-backend, config dev, a per-directory mapping in the CLI's
config), and retire-doppler.py had removed the CLI and that config from
every account. This record retired Doppler as the fabric's store; a
project's use of it was never decided here. The upgrade now removes only
the fabric's own leftover, the secrets-source file.

### Amendment 2026-10-13 — one repository per agent holds its secrets and its settings, in BlueTeam-OU

Each agent's repository now holds its settings beside its secrets, and
lives in BlueTeam-OU: one place per agent, to back up, move or retire, with
access already per login. Settings are what configures the agent (its
bound role, its own model layer, its harness); its working state is not
a setting and is backed up apart (the Proton Drive CLI, a separate
decision). The owner's words, in the coordinator's session: "we should
probably put together agent secrets and configurations while keeping the
uuid identifier in the name", "for settings i mean settings, jobs are not
settings", "both config and secrets repo under blueteam".

### Amendment 2026-10-13 — Commits are signed by each agent's own key, as ADR-057 says

§6 said the shared signing key stays until per-agent signing lands, and
§7 left that signing to its own record. ADR-057 is that record: each
account signs with the signing subkey of its own agent key, in OpenPGP or
SSH form by `policies/signing.json`, timestamped, and checked against the
lineage and the role. The subkey's SSH form is registered as a GitHub
signing key for all 26 agents
(docs/live-checks/2026-10-13-agent-signing-keys-as-ssh.md). The owner's
word, in the coordinator's session: "accepted proceed amending".

### Amendment 2026-10-15 — What belongs to a company is kept in that company's store

ADR-045 gave each client a `secrets_store` in `projects/clients.json`, and
two were created private and empty on 2026-10-09; nothing said who reads
them, how an agent gets what is in them, or how this record's rule 3 ("no
store is encrypted to another agent's key") holds beside them. Meanwhile
the coordinator's own store carries what is no agent's: the Claude-account
templates and their assignments, the keys that mint other keys, the
values every agent shares. A coordinator rebuilt without its home would
take the company's credentials with its key (rule 4).

Rule 10 answers it. A company's store is read by the fabric-coordinator
holders (the role, not the account: a holder change re-encrypts it, as the
charter says authority attaches to the role) and by the owner's recovery
key, which is in that store's `.gpg-id` and in no agent's, because a
company's store has no one agent to be recovered through. Nothing else
changes for an agent: it reads only its own store, and what it needs from
a company's is put into it by its parent, as `provision share` puts a
shared value today, so ADR-042's writers stay the agent and its parent.
Only the fleet's names (`provision share`'s allowlist) stay fleet-wide;
every other granted name, the operator's own included, is a client's,
namespaced and applied to that client's working copies only — ADR-045
rule 6, with rule 9's honest limit: it stops an accident, not the login.
Because any agent can push to a company store, its trusted base is its
holder-signed root, its branch refuses a force-push, and a holder refuses
a head older than the last it verified.

Rejected: an agent as a recipient of its client's store (every agent would
read every client credential it was never granted, and a grant would be a
re-encryption); a company store per role (a role is not a company, and
which client a credential belongs to is what rule 6 needs); and keeping
company credentials in the coordinator's store under a prefix (the case
above: they die with its key).

Drafted by fabric-coordinator for the owner's review in the pull request
that carries it, with the tooling contract (`docs/split/company-stores.md`)
and the names proposed to move (`docs/split/company-store-names.md`).
