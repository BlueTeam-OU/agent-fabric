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
                     launcher's exports), else the checkout this file is
                     in. Not every reader honoured it before this module:
                     those that took their tree from their own location
                     (results, usage, new_agent, resume, ...) pass
                     `engine=code_root()` and keep doing so. Empty
                     counts as unset, as the Python readers took it;
                     `empty_is_set=True` is the one reader that took it
                     as set (gzcoord's paths.fabric_root, after
                     paths.mjs's `??`): an empty root names nothing found.
    code_root()      the checkout this file is in, never the environment:
                     what ships with the code (fresh.py's bash took its
                     own tree, not AGENT_FABRIC_ROOT).
    checkout_root()  the same variable, else <home>/projects/agent-fabric: the account's clone, for the control
                     plane's readers that answer for the account and not for the tree their code was loaded from.
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
    docs/live-checks/
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


def account_clone(home: str, *parts: str) -> str:
    """<home>/projects/agent-fabric[/parts]: where provisioning clones the fabric into an ACCOUNT's home. A place in
    a home directory, not a tree to choose among: `home` is the account's, never the session's environment."""
    return os.path.join(home, "projects", "agent-fabric", *parts)


def sibling_checkout(working_copy: str, environ: Mapping[str, str] | None = None) -> str:
    """AGENT_FABRIC_ROOT when exported (non-empty), else the fabric checkout beside a working copy
    (<working copy>/../agent-fabric): the workspace's layout, for a tool that runs inside a project and has no
    code of the fabric's own to ask."""
    return _env(environ).get(ENV_ENGINE) or os.path.join(working_copy, "..", "agent-fabric")


def checkout_root(home: str, environ: Mapping[str, str] | None = None, *, empty_is_set: bool = False) -> str:
    """The fabric checkout a control-plane account runs on: AGENT_FABRIC_ROOT when exported, else the clone
    provisioning puts at <home>/projects/agent-fabric. Not engine_root(): that falls back to the checkout this
    file is in, and the control plane's readers (agentd, the control ops, fabric-ctl) answer for the ACCOUNT's
    checkout whatever tree their own code was loaded from. Empty counts as unset, except for the readers that took
    the variable by `??` (`empty_is_set`): there it names a root that does not exist, and says so."""
    value = _env(environ).get(ENV_ENGINE)
    if value is None or (value == "" and not empty_is_set):
        return account_clone(home)
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


def personas(name: str, root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    """identities/personas/<name>: the surname list and the claims (agent-fabric ADR-056), the operator's data."""
    return _under(root, environ, engine, "identities", "personas", name)


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


def clients_registry(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "projects", "clients.json")


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


def live_checks_dir(root: str | None = None, environ: Mapping[str, str] | None = None, engine: str | None = None) -> str:
    return _under(root, environ, engine, "docs", "live-checks")


# What leaves for the operator repository (docs/split/move-plan.md §1), as the
# leading path parts of each item. A reader of git objects (`git show
# <rev>:<path>`, cat-file, archive) cannot follow a symlink shim, so it asks
# for the path as the repository stores it. Engine paths are refused rather
# than answered: a reader that asked for one would be told the operator's
# prefix for a file that never moves.
_POLICY_FILES = ("arming", "authority", "auto-mode", "host-load", "hygiene", "signing")
_MOVING = (
    ("identities", "roles"), ("identities", "personas"), ("identities", "keys"),
    ("identities", "agents", "README.md"), ("identities", "recovery.asc"),
    ("projects",), ("runtime", "hosts", "registry.json"),
    *(("policies", f"{name}.json") for name in _POLICY_FILES),
    ("routing", "profiles.json"), ("routing", "policies"),
    ("memory", "domains"), ("memory", "shared"), ("memory", "agents"),
    ("docs", "live-checks"),
)


def operator_prefix(base: str, environ: Mapping[str, str] | None = None) -> str:
    """The operator's tree relative to `base`, with a trailing "/", or "" when
    it is `base` itself (AGENT_FABRIC_OPERATOR unset, empty or equal to it:
    today's layout). An operator outside `base` has no repository-relative
    path there: ValueError, never a guess."""
    value = _env(environ).get(ENV_OPERATOR)
    if not value:
        return ""
    # Lexical, not realpath: the answer names a path inside a git tree, which
    # has no symlinks to resolve.
    rel = os.path.relpath(os.path.abspath(value), os.path.abspath(base))
    if rel == os.curdir:
        return ""
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        raise ValueError(f"{ENV_OPERATOR} {value!r} is not under {base!r}: no repository-relative path")
    return rel.replace(os.sep, "/") + "/"


def git_path(*parts: str, base: str, environ: Mapping[str, str] | None = None) -> str:
    """The path of a move-list item as `git show <rev>:<path>` in the
    repository at `base` spells it: the operator prefix, then `parts`.
    ValueError for a path that is not an item of the move list."""
    if not parts or any(not p or p in (os.curdir, os.pardir) or "/" in p for p in parts):
        raise ValueError(f"not a path of the move list: {parts!r}")
    if not any(parts[:len(item)] == item for item in _MOVING):
        raise ValueError(f"{'/'.join(parts)} is not on the move list: it stays in the engine")
    return operator_prefix(base, environ) + "/".join(parts)
