"""tools/fabric/secretstore/reserved.py — which entry names the fabric manages, and so which are an agent's own.
A part of secret_store.py; secrets_sync.py imports it too, so that the names
set and rm refuse and the names sync reports as "own" can never disagree.

A reserved name is one the fabric writes and applies: the names sync applies
(below), every per-agent name projects/registry.json declares (`agent_env`,
fabric-wide or per project), and every name under CLAUDE_ or FABRIC_. Every
other valid name is the agent's own: set, rm and fabric-secret-run take it,
and sync reports it by name only and writes it nowhere.

A registry that cannot be read is no answer: reserved() raises, and a caller
refuses rather than take a name it cannot classify (the coordinator's P2,
2026-10-07)."""
from __future__ import annotations

import json

import roots

ENV_NAMES = ["OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN"]
GIT_NAMES = {"GIT_USER_NAME": "user.name", "GIT_USER_EMAIL": "user.email",
             "GIT_SIGNING_KEY": "user.signingkey", "GIT_GPG_PROGRAM": "gpg.program"}
SSH_NAMES = ["SSH_PRIVATE_KEY", "SSH_PUBLIC_KEY"]
IDENTITY_NAMES = ["AGENT_LOGIN", "AGENT_HOST"]
# Never written into secrets.env, whatever the registry declares: ~/.bashrc
# sourced that file, so an exported name was in every shell and subagent of
# the account, and a reviewer printed its environment with the operator's
# signing key in it (rotated, #95). No shell sources secrets.env any more
# (ADR-038 rule 9), but a file every tool may read is still no place for
# the key that signs fleet actions. fabric-ctl decrypts it from the store
# when it signs (runtime/control/ctl.mjs signingKey()). Known, so a store
# holding it is not "unexpected"; and since the file is rewritten whole,
# the next sync drops a line an older one wrote.
STORE_ONLY = ["FABRIC_CONTROL_SIGNING_KEY"]
ALL_NAMES = IDENTITY_NAMES + ENV_NAMES + list(GIT_NAMES) + SSH_NAMES
PREFIXES = {"CLAUDE_": "the Claude account assignment (fabric-accounts) and the harness",
            "FABRIC_": "the fabric itself"}


class RegistryUnreadable(Exception):
    """projects/registry.json could not be read or is not a registry."""


def registry_agent_env(root: str | None = None, engine: str | None = None) -> dict[str, str]:
    """Every per-agent name the registry declares, with where: "agent_env"
    for the fabric-wide table, "projects.<id>.agent_env" for a project's."""
    path = roots.projects_registry(root or None, engine=engine)
    try:
        with open(path, encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError) as e:
        raise RegistryUnreadable(f"{path}: {e.__class__.__name__}") from None
    if not isinstance(reg, dict) or not isinstance(reg.get("projects") or {}, dict):
        raise RegistryUnreadable(f"{path}: not a registry")
    out: dict[str, str] = {}
    holders = [("agent_env", reg)] + [(f"projects.{k}.agent_env", v) for k, v in (reg.get("projects") or {}).items()]
    for where, holder in holders:
        table = holder.get("agent_env") if isinstance(holder, dict) else None
        if table is not None and not isinstance(table, dict):
            raise RegistryUnreadable(f"{path}: {where} is not an object")
        for n in table or {}:
            out.setdefault(n, where)
    return out


def reserved(name: str, root: str | None = None, engine: str | None = None) -> str | None:
    """Who manages NAME, as a phrase for a refusal; None when it is the
    agent's own. Raises RegistryUnreadable when that cannot be told."""
    if name in IDENTITY_NAMES or name in GIT_NAMES or name in SSH_NAMES:
        return "the agent's parent, which writes it at enrolment (fabric-secrets store put), and fabric-secrets sync"
    if name in ENV_NAMES:
        return "the coordinator, which shares it (fabric-secrets provision share), and fabric-secrets sync"
    if name in STORE_ONLY:
        return "fabric-ctl keygen"
    for prefix, who in PREFIXES.items():
        if name.startswith(prefix):
            return f"{who} (every {prefix} name)"
    where = registry_agent_env(root, engine).get(name)
    if where:
        return f"projects/registry.json ({where}) and fabric-secrets sync"
    return None
