# Provisioning — what an agent account needs from the control plane

An agent is a Linux login. Giving a role its own account is a host
action, and most of it is the deployment's (SSH and forge credentials,
commit signing, the toolchain of the projects it will work on, data
areas): that runbook lives with the deployment. This is the part that is
the control plane's, the same for every deployment and every project.

## The layout every account has

```text
~/projects/
├── CLAUDE.md                 workspace instructions: one line and an import
│                             of agent-fabric/CLAUDE.md (written by bootstrap)
├── .claude/settings.json     the hooks, wired to the checkout below (bootstrap)
├── agent-fabric/             this repository — a checkout per account
└── <working copy>/…          the managed repositories the account works in
```

The account name identifies the agent (`bin/fabric-whoami`); the
directory it stands in identifies context, never identity.

## The steps, per account

**One command does all of it** (fabric-coordinator, from its own login).
It has two halves: the orchestrator, `new-agent.sh`, runs where the
coordinator is and keeps what only the coordinator holds — the
registries, its own store (the account's parent, ADR-038), the API keys; the host half,
`new-agent-worker.sh`, runs on the host the account lives on
(`runtime/hosts/registry.json`; `--host` places a new account) through
`runtime/hostexec/` — directly on this host, over ssh to any other — in
two phases around the secrets step. The host names itself and is
refused if it answers as anything but its registry id. The host half
starts with a host audit: a Qubes AppVM keeps only `/home` and
`/usr/local` across a reboot, so the rpm tools the fabric itself calls
(git, gh, node, npm, python3, jq, gpg) are checked and a missing one is
named with its package for the TemplateVM; the account's own tools go
under its `~/.local`.
What a project needs beyond that is the project's to say —
`projects/<id>/integration/provisioning/host-check.sh`, run on the host
for each `--project`:

```sh
runtime/provisioning/new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--dry-run]
runtime/provisioning/new-agent.sh <login> <role> --project <id> --project <id>
runtime/provisioning/new-agent.sh <login> <role> --host <host-id> --project <id>   # on another host
```

Every step is `must` (a failure stops the run, named; nothing after it
runs), `probe` (a question) or `best_effort` (one warning) —
`test_new-agent.sh` runs the whole sequence against fakes on both
backends and injects a failure at each `must`. Idempotent — every step is checked before it is done, so it is also how
an account that came out short is completed. In order: the Linux account
(home 700, the shared-cache group, persisted across the host's reboot —
linger, and on Qubes the record snapshot under `/rw`,
`persist-accounts.sh`); the home skeleton, then `claude` and `ori`
installed as the account the way their vendors say (`claude.ai/install.sh`
at the version the fleet pins in `runtime/claude-code/harness.json`, so a
new account starts where the others are (agent-fabric ADR-009); `--claude`
overrides it with a version, `stable` or `latest`, and with no pin
readable it is the vendor's latest — and `openrouter.ai/labs/ori/install.sh`; an installer that fails
fails the script, nothing is copied from another account); GitHub's host key in
`known_hosts`; `~/projects/agent-fabric` over https (the fabric is
public; the account has no key yet); its key and store —
`store-enroll.sh <login> --born-now`, made on its host and certified by
the coordinator — filled by the coordinator as its parent
(`fabric-secrets provision identity`, `share`, then `issue-key
openrouter` and `issue-key openai` **once each**: a key of the account's
own on each API; presence in its store is the check) — and the first
sync, as the account; every
`--project` cloned as the account over SSH from the remote the registry
names; `bootstrap.sh`; `bin/fabric-role bind <role>`; the toolchain each
project's lockfile declares (pnpm under `~/.local`, `pnpm install`,
`npm ci`, a venv); then verification (`fabric-secrets status`, `gh`, SSH
to every origin, the git identity, `launch --print` on both providers)
and the short list of what only a person at a terminal can do: the GPG
secret key (a passphrase prompt), `~/.claude/.credentials.json` for the
plain-claude path (a credential copy a classifier refuses an agent), and
the workspace-trust dialog at the first interactive launch. It was
written on 2026-09-15 after two accounts walked by hand came out short —
a missing binary, a root-owned `~/.local/bin`, an untrusted host key, no
toolchain, and a `fill-from` that copied the coordinator's admin keys.

What the steps are, when done by hand:

1. **Clone agent-fabric** beside the working copies:
   `git clone git@github.com:gzapi-org/agent-fabric.git ~/projects/agent-fabric`.
2. **Run bootstrap** as the account:
   `~/projects/agent-fabric/runtime/claude-code/bootstrap.sh`. It writes
   the workspace `CLAUDE.md` and `.claude/settings.json`, installs
   user-scope the capability-class agent files, the
   review class's Bash fence and the `subagent-dispatch` skill, and sets
   `core.hooksPath` on this checkout and on every registered working copy
   beside it (the attribution ban and the `.agent-fabric/` fence).
   Idempotent; re-run after pulling.
3. **Bind a role once**, as the account, from a login shell, inside its
   working copy: `~/projects/agent-fabric/bin/fabric-role bind <role>`
   (`tools/fabric/role.py`; refused inside a session). The binding lives
   under `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/`;
   the launcher refuses to run without one and renders the role into the
   session's system prompt. A different role later is a rebind here and a
   relaunch.
4. **Enrol the identity's secrets** (fabric-coordinator, from its own
   login): `runtime/provisioning/secrets/store-enroll.sh <login>`, then
   `fabric-secrets provision` — see "Secrets" below. After it,
   `OPENROUTER_API_KEY`, `GH_TOKEN`,
   `OPENAI_API_KEY` and the GZCoord token are in the account's
   environment from `~/.config/agent-fabric/secrets.env`, git identity
   and signing are set, and `runtime/openrouter/launch` (with the `ori`
   CLI on `PATH`) runs from the working copy
   (`runtime/openrouter/README.md`). `provision share` copies only an
   allowlist of names and refuses the coordinator's own credentials
   (`*_ADMIN_KEY`, `*_PROVISIONING_KEY`, the templates, the signing key)
   even when named; a per-login name (the API keys, a port offset) has
   its own step.

The agent files (step 2) are written per account by
`runtime/claude-code/install-agent-files.sh`, which `bootstrap.sh` runs
for the launch's provider, so a `moveto` (pull + bootstrap) refreshes
them; there is no bulk installer any more (the one that existed knew
three classes and wrote stale files). `moveto/` opens a shell as another
account in its working copy.
`rename-working-copy.sh <login> <old> <new>` moves a working copy and
carries the account's Claude Code history with it — transcripts, memory,
`~/.claude.json` project entry, prompt history, the binding — since all of
it is keyed by the clone's absolute path (2026-09-14: every clone renamed
from `~/projects/<login>` to `~/projects/gzapp`; a live session, or a
tree mid-work, is refused).

## Secrets

An identity's secrets are recorded in **its own store** (ADR-038): a
pass-format git repository `<org>/agent-fabric-secrets-<agent-id>`
(ADR-039), each entry encrypted to the agent's own key, cloned at
`~/.local/share/agent-fabric/secrets`. The key is made in the account and
certified by its parent, the coordinator, which keeps a mirror of the
store to write into it — `put` encrypts to the child's committed key, so
the parent cannot read what it wrote. Nothing else is held for it: no
token, no service. What the store holds is derived into the places the
tools read:

| name | consumed as |
|---|---|
| `AGENT_LOGIN`, `AGENT_HOST` | `fabric-secrets sync` refuses a store whose `AGENT_LOGIN` is not the login running it — the invariant, enforced at the secret boundary |
| `OPENROUTER_API_KEY`, `GH_TOKEN`, `CLAUDE_BRIDGE_AUTH_TOKEN`, `SERPAPI_API_KEY`, `BRAVE_SEARCH_API_KEY` (language-culture logins: the locale search tools, `runtime/mcp/websearch-locale`) | exported from `~/.config/agent-fabric/secrets.env` (0600), sourced by `~/.bashrc` |
| `GIT_USER_NAME`, `GIT_USER_EMAIL`, `GIT_SIGNING_KEY`, `GIT_GPG_PROGRAM` | `git config --global` (strings; the signing key material stays in the keyring) |
| `SSH_PRIVATE_KEY`, `SSH_PUBLIC_KEY` | `~/.ssh/id_ed25519(.pub)`, written only when absent (`--force` replaces) |
| a project's `agent_env` names (`projects/registry.json`; gzapp: `GZAPP_PORT_OFFSET`) | exported from `secrets.env` when the store has them — per-login values that are not secrets but belong to the identity, never reported missing |

- `bin/fabric-secrets sync` (as the account) pulls and applies; `status`
  reports presence, modes and ages — neither prints a value.
- `secrets/store-enroll.sh <login> [--host <id>] [--born-now]`
  (coordinator): the account's id, its private repository, its key and
  store made on its host, the certification, the mirror. Then
  `fabric-secrets store recovery-copy` as the account and `store backup`
  as the coordinator (ADR-038 §6).
- `fabric-secrets provision` (coordinator, the parent) fills a child's
  store: `identity <login> --host <id>` (AGENT_LOGIN, AGENT_HOST);
  `share <login…|all>` (the coordinator's own value of each shared name —
  GH_TOKEN, the relay token, the git strings, the SSH key pair — where
  the child lacks it); `issue-key openrouter|openai <login…>` (a key of
  the login's own, minted with the coordinator's `OPENROUTER_PROVISIONING_KEY`
  or `OPENAI_ADMIN_KEY` from its store and put straight into the child's;
  both providers then report spend per key, i.e. per agent). A name the
  child holds is left alone unless `--replace`. Only names, statuses and
  fingerprints are printed.
- Rotation of a shared value: `fabric-secrets store set NAME` in the
  coordinator's own store (the value on stdin), then `fabric-secrets
  provision share all --name NAME --replace`, then `fabric-ctl all
  secrets-sync`. A value only one login holds: `fabric-secrets store put
  <login> NAME`, then `fabric-ctl <login> secrets-sync`.
- Which Claude account a login runs on: `fabric-accounts assign`
  (ADR-031), a template's token from the coordinator's store into the
  login's.

## What does not transfer between accounts

Session memory is the account's (`~/.claude/projects/…/memory/`); a drain
distils it into the corpus, nothing copies it across. Runtime bindings,
role history and local model overrides are per account for the same
reason: they say what *this* agent is doing.
