#!/usr/bin/env python3
"""tools/fabric/roots.py — the engine root, the operator root, and where
instance data lives under the latter.

agent-fabric is being split into a public ENGINE (code, tests, the
schemas, the default dictionary) and a private OPERATOR repository (what
describes one fleet: roles, registries, policies, routing overlays,
memory, decisions, keys). Until the files move, both are this checkout;
this module is the one place that knows which is which, so a reader of
instance data asks it and the later move is a change here.

    engine_root()    AGENT_FABRIC_ROOT when set (a test, a fixture, the
                     launcher's exports — every tool already honoured
                     it), else the checkout this file is in. Empty
                     counts as unset, as the Python readers took it;
                     `empty_is_set=True` is the one reader that took it
                     as set (gzcoord's paths.fabric_root, after
                     paths.mjs's `??`): an empty root names nothing found.
    code_root()      the checkout this file is in, never the environment:
                     what ships with the code (fresh.py's bash took its
                     own tree, not AGENT_FABRIC_ROOT).
    operator_root()  AGENT_FABRIC_OPERATOR when set and non-empty, else
                     engine_root().

Every helper below takes `environ` (a mapping, default os.environ: the
launcher reads the environment of the session it builds, not its own),
`root` (an explicit operator tree, which wins over everything: a tool's
--root names the tree it means) and `engine` (the engine tree the caller
was handed; it stands in for the environment's engine root, and an
exported AGENT_FABRIC_OPERATOR still outranks it). A helper never creates
or reads anything; it returns a path. A missing root is a path that
does not exist, not a fallback to another tree.

The instance data (the lists are the owner's, 2026-10-07):
    identities/roles/catalog.json, identities/roles/<role>/
    projects/registry.json, projects/<id>/integration/
    runtime/hosts/registry.json   (AGENT_FABRIC_HOSTS_REGISTRY overrides)
    policies/*.json
    routing/profiles.json         (the overlays; capabilities stay engine)
    memory/
    docs/adr/
    identities/keys/
"""
from __future__ import annotations

import os
from collections.abc import Mapping

ENV_ENGINE = "AGENT_FABRIC_ROOT"
ENV_OPERATOR = "AGENT_FABRIC_OPERATOR"
ENV_HOSTS_REGISTRY = "AGENT_FABRIC_HOSTS_REGISTRY"

# tools/fabric/roots.py -> the checkout. Real path: the commands are links
# in ~/.local/bin, and a link's directory is not the checkout's.
_CODE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def _env(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def code_root() -> str:
    return _CODE_ROOT


def engine_root(environ: Mapping[str, str] | None = None, *, empty_is_set: bool = False) -> str:
    value = _env(environ).get(ENV_ENGINE)
    if value is None or (value == "" and not empty_is_set):
        return _CODE_ROOT
    return value


def operator_root(environ: Mapping[str, str] | None = None, *, empty_is_set: bool = False,
                  engine: str | None = None) -> str:
    """`engine` is for a caller that was handed its engine tree (status.py's
    `root`, a launcher's fabric_root): with no operator exported, that tree
    is the operator's too, not the environment's."""
    value = _env(environ).get(ENV_OPERATOR)
    if value:
        return value
    if engine is not None:
        return engine
    return engine_root(environ, empty_is_set=empty_is_set)


def _under(root: str | None, environ: Mapping[str, str] | None, engine: str | None, *parts: str) -> str:
    return os.path.join(operator_root(environ, engine=engine) if root is None else root, *parts)


def role_catalog(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "roles", "catalog.json")


def roles_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "roles")


def role_dir(role: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "roles", role)


def locale_dir(role: str, suffix: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "roles", role, "locale", suffix)


def keys_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "keys")


def recovery_key(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "identities", "recovery.asc")


def projects_registry(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "projects", "registry.json")


def projects_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "projects")


def project_integration(project: str, *parts: str, root: str | None = None,
                        environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "projects", project, "integration", *parts)


def hosts_registry(root: str | None = None, environ: Mapping[str, str] | None = None,
                   engine: str | None = None, *, empty_is_set: bool = False) -> str:
    """AGENT_FABRIC_HOSTS_REGISTRY (a test, a one-off fleet) outranks the
    tree; an explicit `root` outranks neither: a tool handed a root and
    an exported registry has always read the registry. Set but empty is
    unset, except for the control plane's Node readers, which took `??`:
    there it names a registry that does not exist, and says so."""
    override = _env(environ).get(ENV_HOSTS_REGISTRY)
    if override or (override is not None and empty_is_set):
        return override
    return _under(root, environ, engine, "runtime", "hosts", "registry.json")


def policy(name: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "policies", name)


def policies_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "policies")


def routing_profiles(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "routing", "profiles.json")


def routing_policy(name: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "routing", "policies", name)


def memory_dir(*parts: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "memory", *parts)


def adr_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "docs", "adr")
