"""tools/fabric/provisioning/new_agent_args.py — new-agent's command line: its
usage, its help, the shapes it checks a flag's value against, and the parse
(ADR-040 Wave 5; carried from tools/fabric/new_agent.py). A refusal is an Exit
with the status and the line the orchestrator prints; nothing here touches the host."""
from __future__ import annotations

import re
import sys


# The value reaches the worker's as_login eval inside single quotes, so a
# suffix may carry no quote, semicolon or other shell character — only
# what a real pre-release or build tag holds (review of #34).
CLAUDE_TARGET = re.compile(r"stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?")


# A template's slug as fabric-secrets store templates names it (its SLUG_RE);
# the fingerprint, sha256[:12] of the token, as it answers it.
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


FINGERPRINT = re.compile(r"[0-9a-f]{12}")


USAGE = ("usage: new-agent.sh <login> <role> (--claude-account <slug> | --no-claude-account) [--host <id>] "
         "[--project <id>]... [--claude VERSION|stable|latest] [--no-signing-key] [--dry-run]\n"
         "       new-agent.sh <login> --human [--host <id>] [--dry-run]\n")


NO_ACCOUNT_CHOICE = ("new-agent: name the Claude account it starts on: --claude-account <slug> (fabric-accounts "
                     "templates), or --no-claude-account for the broker path only")


HELP = """\
runtime/provisioning/new-agent.sh — give a role its own account on this
host: everything the control plane can do without a person at a
terminal, in order, idempotently, then the short list of what only a
person can do. Run by a fabric-coordinator holder from its own login
(the account steps go through sudo; the secrets step is the
coordinator's as the account's parent, ADR-038).

  runtime/provisioning/new-agent.sh <login> <role> (--claude-account <slug> | --no-claude-account) [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--no-signing-key] [--dry-run]
  runtime/provisioning/new-agent.sh <login> --human [--host <id>] [--dry-run]

  new-agent.sh <login> <role> --claude-account <slug> --project <id> --project <id>
  new-agent.sh <login> <role> --claude-account <slug> --host <host-id> --project <id>      # on another host
  new-agent.sh <login> <role> --no-claude-account --project <id>   # the broker path only
  new-agent.sh <login> --human     # a person's login (ADR-044): placed with kinds "human" first

On a terminal, an agent's last step imports the fleet's signing key
(gpg's pinentry asks its passphrase); without one, or with
--no-signing-key, the closing prints the two lines a person runs.

The Claude account it starts on is a template in this login's store
(fabric-accounts templates): checked before any account is made,
its token written into the new store before the first sync, and its
fingerprint compared in finish (ADR-031).

TWO HALVES (review, 2026-09-16). This script is the ORCHESTRATOR: it
runs on the coordinator's host and keeps what only the coordinator
holds — the registry, its own store, the API keys. The
HOST half, runtime/provisioning/new-agent-worker.sh, runs on the host
the account is placed on (runtime/hosts/registry.json; --host names a
new placement) through runtime/hostexec/hostexec — directly on this
host, over ssh to any other — in two phases around the secrets step:
`prepare` (0-4) and `finish` (6-10). The host names itself (`hostname
-s`, checked against the registry id) and the coordinator never stamps
a host it is not on.

WHY THIS EXISTS. The host runbook (the managed project's docs/host/
PROVISIONING.md) is twelve sections a person walks by hand, and twice
on 2026-09-15 an account was walked through it in a session and came
out short: a claude binary never installed, a root-owned ~/.local/bin,
the GitHub host key never trusted so every SSH step failed as a
password prompt, pnpm and node_modules absent, and — the one that
mattered — a fill-from that copied the coordinator's admin keys into
the new account's config. Each of those is one line here, checked
before it is done, so the second account costs what the first did.

WHAT IT DOES, in order (each step is skipped when already true):
  0. the host: what this AppVM must already have and what it can hold.
     A Qubes AppVM keeps only /home and /usr/local across a reboot; a
     package is the TemplateVM's (dnf there, not here). So: the rpm
     tools the fabric and the projects use (git, gh, node, npm,
     python3, jq, gpg) are audited and a missing one is named with its
     package for the template; the account's own tools go under its
     ~/.local. What
     a PROJECT needs of the host beyond that is the project's own
     integration/provisioning/host-check.sh, run in finish. [worker: prepare]
  1. the Linux account (useradd), home 700, the shared-cache group, and the
     account persisted across the host's reboot (linger; on Qubes the record
     snapshot under /rw — persist-accounts.sh)
  2. ~/.ssh ~/.claude ~/.config/gh ~/.local/{bin,share}, owned by the
     account; claude and ori installed AS THE ACCOUNT the way their
     vendors say — `curl -fsSL https://claude.ai/install.sh | bash -s --
     <version>` — at the version the fleet pins in
     runtime/claude-code/harness.json (what `fabric-ctl … upgrade
"""


class Exit(Exception):
    def __init__(self, code: int, msg: str | None = None):
        super().__init__(msg)
        self.code, self.msg = code, msg


def say(msg: str) -> None:
    print(f"new-agent: {msg}", file=sys.stderr, flush=True)


def die(msg: str) -> "NoReturn":  # noqa: F821
    raise Exit(1, f"new-agent: {msg}")


def parse(argv: list[str]) -> dict:
    o = {"dry": False, "login": "", "role": "", "projects": [], "claude": "", "host": "", "claude-account": None,
         "no-claude-account": False, "human": False, "no-signing-key": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--host", "--claude", "--project", "--claude-account"):
            if i + 1 >= len(argv):
                raise Exit(1, f"new-agent: {a} needs a value")
            v = argv[i + 1]
            i += 1
            if a == "--project":
                o["projects"].append(v)
            else:
                o[a[2:]] = v
        elif a.startswith(("--host=", "--claude=", "--project=", "--claude-account=")):
            name, v = a[2:].split("=", 1)
            if name == "project":
                o["projects"].append(v)
            else:
                o[name] = v
        elif a == "--dry-run":
            o["dry"] = True
        elif a in ("--no-claude-account", "--human", "--no-signing-key"):
            o[a[2:]] = True
        elif a in ("-h", "--help"):
            raise Exit(0, None)
        elif a.startswith("-"):
            raise Exit(2, f"new-agent: unknown flag {a}")
        elif not o["login"]:
            o["login"] = a
        elif not o["role"]:
            o["role"] = a
        else:
            raise Exit(2, f"new-agent: unexpected argument {a}")
        i += 1
    if o["human"]:
        if o["role"]:
            raise Exit(2, f"new-agent: a human login has no role (ADR-044): new-agent.sh {o['login']} --human")
        if o["claude-account"] is not None or o["no-claude-account"] or o["claude"] or o["projects"]:
            raise Exit(2, "new-agent: --human takes --host and --dry-run only: a human has no Claude account, no claude "
                          "and no project clones (ADR-044)")
        if not o["login"]:
            raise Exit(2, USAGE.rstrip("\n"))
        return o
    if not (o["login"] and o["role"]):
        raise Exit(2, USAGE.rstrip("\n"))
    if o["claude"] and not CLAUDE_TARGET.fullmatch(o["claude"]):
        raise Exit(2, "new-agent: --claude takes stable, latest or a version")
    given = o["claude-account"] is not None
    if given == o["no-claude-account"]:
        raise Exit(2, NO_ACCOUNT_CHOICE)
    if given and not SLUG.fullmatch(o["claude-account"]):
        raise Exit(2, f"new-agent: --claude-account {o['claude-account']!r} is not an account slug (lowercase, digits, "
                      "dashes; fabric-accounts templates)")
    return o
