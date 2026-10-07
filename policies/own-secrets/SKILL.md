---
name: own-secrets
description: "Keep a secret of your own — an API key, a token, a password a tool of yours needs — in your own encrypted store: add it without its value ever entering the conversation, use it in one command's environment, list it by name, remove it when nothing uses it. Load it before you handle any credential, when a person or a provider gives you one, when a tool asks for a key, or when asked how agents store, use or delete secrets."
---

# Your own secrets

Every login has its own encrypted store, a git repository of gpg files
that only that login's key decrypts. Two kinds of name live in it:

- **managed** — what the fabric writes and applies for you (the relay
  token, the GitHub token, git identity, the per-agent names the
  registry declares, anything under `CLAUDE_` or `FABRIC_`). These reach
  the tools that read them through `fabric-secrets sync`. You never set,
  remove or run with one; the commands below refuse them.
- **own** — every other valid name. Yours to add, use and remove.

The one rule above the rest: **a value never passes through you.** Not in
a message, not in argv, not in a file in the tree, not printed to check
it. You handle names; the value goes from where it is made straight into
the store, and from the store straight into the one process that needs
it.

## Add

```sh
<producer> | fabric-secrets store set NAME
```

The value is read from stdin, so it never appears in argv or the process
list. The producer is whatever makes the value without showing it: a
provider's CLI that mints a token on stdout, or a file the person left
for you outside every working copy, mode 0600 (`< ~/name`, then delete
the file) — never in a repository, where `git add -A` would stage it
before you delete it. An empty stdin — a
producer that failed — is refused, not stored as an empty secret.

When a **person** has the value, they type it, not you. Ask them to
run, in a terminal as your login (your tab in the fleet's terminal, or
`moveto <your login>`):

```text
fabric-secrets store set NAME
```

On a terminal it asks twice without echo. Not through the session's
`!` prefix: whether that gives the command a terminal is unverified,
and without one the value is read from stdin. Never ask anyone to paste a
value into the conversation; if one arrives there anyway, it is leaked —
say so and ask for it to be rotated at its provider.

`set` commits signed and pushes; setting an existing name replaces it.
`NAME` is an environment-variable name (`EXAMPLE_API_KEY`), chosen for
the variable the consuming tool reads. A name the fabric manages is
refused; `fabric-secrets status --json` lists the managed names it
applies and your own under `own`.

## Use

```sh
fabric-secret-run NAME[,NAME...] -- <command> [args...]
```

Each name is decrypted into that command's environment only, and the
command replaces the wrapper. Your shell, your session and your
subagents never hold it. Run a tool that reads the variable itself;
never one that prints it (`echo`, `env`, a debug flag).

`fabric-secret-run` asks each time: it runs whatever follows `--`, so no
standing rule can allow it. That ask is the point, not an obstacle.

Exit 2 with a `fabric-secret-run:` line on stderr, naming the name and
never the value, means nothing ran: a malformed, managed, absent or
undecryptable name, or a registry it could not read. 126 and 127 mean
the command could not be executed or was not found. Any other status —
an exit 2 without that line included — is the command's own.

## See what you hold

```sh
fabric-secrets store names        # every entry, names only
fabric-secrets status --json      # sync state; your own names under "own"
```

There is no command that prints a value, and none is needed.

## Remove

```sh
fabric-secrets store rm NAME
```

Commits signed and pushes. Removal is hygiene: what the store no longer
holds is no longer used. Git history keeps the old file, so a value that
may have leaked is not made safe by `rm` — rotate it at its provider,
then `set` the new one.

## What the operator can check

`fabric-ctl <login> secrets-selftest` runs `fabric-secrets selftest` as
your login: a canary own name is set, read through `fabric-secret-run`,
removed, and its absence checked. Only the verdict and the steps leave
the account. You can run `fabric-secrets selftest` yourself after
anything about your store changed.

## Never

- a value in a message, a commit, a PR, a log, a memory file or a test
  fixture — describe a secret by name and shape;
- `env`, `printenv`, `set` or `cat` of a secrets file to check that a
  value arrived — `fabric-secrets status` and the consuming tool's own
  success are the check;
- `--managed` on your own initiative: it is for the operator's rotation
  recipe;
- a secret in a `.claude/settings.local.json` `env` block, which every
  process of every session inherits.
