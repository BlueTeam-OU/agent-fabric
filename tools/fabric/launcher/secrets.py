"""tools/fabric/launcher/secrets.py — the synced secrets settled into the session's environment.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import os
import shlex
from fabric_launcher.base import say


def synced_values(home: str, name: str = "secrets.env") -> dict[str, str]:
    """The `export NAME=value` lines fabric-secrets sync wrote, parsed as the
    shell would; an unreadable line is skipped, never guessed."""
    out: dict[str, str] = {}
    try:
        with open(f"{home}/.config/agent-fabric/{name}", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("export ") and "=" in line:
                    try:
                        k, v = shlex.split(line[len("export "):])[0].split("=", 1)
                    except (ValueError, IndexError):
                        continue
                    out[k] = v
    except OSError:
        pass
    return out


def synced_oauth_token(home: str) -> str:
    return synced_values(home).get("CLAUDE_CODE_OAUTH_TOKEN", "")


# The other way round: a login moved to a Claude-account template has
# CLAUDE_CODE_OAUTH_TOKEN in its synced record (and, from a shell older
# than ADR-038 rule 9, in its environment), and a broker
# session must never hold it — whichever credential the harness prefers
# with a base URL set, an Anthropic subscription token has no business in
# a process whose requests go to a third party (review of #33). Dropped
# unconditionally on the broker path, by name.
# Which Claude account a plain-claude session runs on is the login's synced
# record, not the shell this launcher inherited: a shell opened before
# `fabric-accounts assign` moved the login still holds the old token (or
# none), and a relaunch from it — including the upgrade's automatic resume
# — would start on the old account (2026-09-25, devex-tooling). Read from
# ~/.config/agent-fabric/secrets.env at every launch; absent there, an
# inherited one is dropped. Said by name when it replaces or drops one.
def settle_oauth_token(provider: str, home: str) -> None:
    env = os.environ
    if provider == "anthropic":
        synced = synced_oauth_token(home)
        if synced:
            if env.get("CLAUDE_CODE_OAUTH_TOKEN") and env["CLAUDE_CODE_OAUTH_TOKEN"] != synced:
                say("launch: CLAUDE_CODE_OAUTH_TOKEN taken from the login's synced record, not the older one "
                    "this shell inherited")
            env["CLAUDE_CODE_OAUTH_TOKEN"] = synced
        elif "CLAUDE_CODE_OAUTH_TOKEN" in env:
            del env["CLAUDE_CODE_OAUTH_TOKEN"]
            say("launch: dropped the CLAUDE_CODE_OAUTH_TOKEN this shell inherited — the login's synced record "
                "has none")
    elif "CLAUDE_CODE_OAUTH_TOKEN" in env:
        del env["CLAUDE_CODE_OAUTH_TOKEN"]
        say("launch: the broker path — dropped CLAUDE_CODE_OAUTH_TOKEN (a Claude-account template's token "
            "never reaches a broker session)")


# The session gets its own credential and no other secret (ADR-038 rule 9).
# No shell sources secrets.env any more, but a launch from a shell opened
# before that sync — or from inside an older session — still inherits every
# synced name, and the session would hand them to every Bash call and
# subagent. Each name sync wrote is dropped here, except the plain ones
# (env.sh) and the one credential this provider's harness signs in with,
# which comes from the file, not the shell. The fixed names are dropped
# even with no file, since an inherited shell is exactly the stale case.
SYNCED_SECRETS = ("OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


HARNESS_CREDENTIAL = {"anthropic": "CLAUDE_CODE_OAUTH_TOKEN", "openrouter": "OPENROUTER_API_KEY"}


# What the harness itself expands, not a Bash call: a project's .mcp.json
# names the relay token in its claude-bridge header, and the
# harness fills ${CLAUDE_BRIDGE_AUTH_TOKEN} from its own environment. Set
# from the file, like the sign-in; the SessionStart seal still unsets it
# for every Bash call (review of #100).
HARNESS_EXPANDS = ("CLAUDE_BRIDGE_AUTH_TOKEN",)


def settle_secrets(provider: str, home: str) -> None:
    env = os.environ
    synced, plain = synced_values(home), synced_values(home, "env.sh")
    keep = HARNESS_CREDENTIAL.get(provider)
    if keep == "OPENROUTER_API_KEY" and synced.get(keep):
        env[keep] = synced[keep]
    for n in HARNESS_EXPANDS:
        if synced.get(n):
            env[n] = synced[n]
    names = (set(synced) | set(SYNCED_SECRETS)) - set(plain) - {keep} - {n for n in HARNESS_EXPANDS if synced.get(n)}
    dropped = sorted(n for n in names if n in env)
    for n in dropped:
        del env[n]
    if dropped:
        say("launch: the session holds only its own credential — dropped what this shell inherited: "
            + " ".join(dropped))
