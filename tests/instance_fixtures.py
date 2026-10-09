"""Instance data a test builds for itself, never the checkout's live files
(agent-fabric ADR-045 §5 rules 2-3): what more than one test needs, kept in
one place. Each fixture holds only what its readers read."""
from __future__ import annotations

import json
import os
import shutil

# The project ids tools/fabric/adr.py reads from projects/registry.json, to
# tell another project's cited ADR ("gzapp's ADR-075") from this one's. The
# decision records name gzapp alone; a record that comes to cite another
# project fails the clean-corpus cases ("cites ADR-NNN, which does not
# exist") until its id is added here. fixture-proj is in no live registry:
# a case cites it, so adr.py reading the live registry fails that case.
ADR_REGISTRY = {"projects": {"agent-fabric": {}, "gzapp": {}, "fixture-proj": {}}}


# Lint judges every registry with projects (ADR-045 §5 rule 5): each names a
# client that clients.json beside it defines. A fixture registry gets this one.
FIXTURE_CLIENT = "fixture-client"


def with_client(doc: dict) -> dict:
    """`doc` with FIXTURE_CLIENT on each project that names no client."""
    projects = doc.get("projects")
    if not isinstance(projects, dict):
        return doc
    return {**doc, "projects": {pid: ({"client": FIXTURE_CLIENT, **e} if isinstance(e, dict) else e)
                                for pid, e in projects.items()}}


def write_clients(directory: str) -> str:
    """<directory>/clients.json defining FIXTURE_CLIENT; its path."""
    return write_json(os.path.join(directory, "clients.json"), {"version": 1, "clients": {FIXTURE_CLIENT: {}}})


def write_registry(directory: str, doc: dict = ADR_REGISTRY) -> str:
    """<directory>/registry.json holding `doc` with a client on each project,
    and the clients.json that defines it; the registry's path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "registry.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(with_client(doc), fh)
    write_clients(directory)
    return path


# A projects registry for the tests that classify secret names or look a
# project's remote up: what secretstore/reserved.py, secrets_sync.py,
# new_agent.py, results.py and commit_class.py read from it, and no more.
# Names are the managed ones the cases assert on (OPENAI_API_KEY, the gzapp
# port offset); fixture-proj is in no live registry, so a reader that took
# the live one finds neither it nor its remote.
SECRETS_REGISTRY = {
    "version": 1,
    "agent_env": {"OPENAI_API_KEY": "a fixture key, one per login",
                  "OPENROUTER_API_KEY": "a fixture key, one per login",
                  "CLAUDE_CODE_OAUTH_TOKEN": "the Claude account's token, a fixture",
                  "FABRIC_CONTROL_SIGNING_KEY": "the operator's signing key, store only"},
    "projects": {
        "gzapp": {"remotes": ["git@github.com:fixture-org/gzapp.git", "https://github.com/fixture-org/gzapp"],
                  "agent_env": {"GZAPP_PORT_OFFSET": "the login stack's port offset"},
                  "plain_env": ["GZAPP_PORT_OFFSET"]},
        "agent-fabric": {"remotes": ["git@github.com:fixture-org/agent-fabric.git",
                                     "https://github.com/fixture-org/agent-fabric"]},
        "fixture-proj": {"remotes": ["git@github.com:fixture-org/fixture-proj.git"]},
    },
}

# A hosts registry: one host, one placed login, the logins' kinds as ADR-044
# reads them (a login `kinds` does not name is an agent).
HOSTS_REGISTRY = {"version": 1, "hosts": {}, "placement": {"fixture-login": "fixture-host"}, "kinds": {}}


def write_json(path: str, doc: dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


def write_secrets_instance(tree: str) -> None:
    """SECRETS_REGISTRY and HOSTS_REGISTRY at their places in an operator
    or fabric tree."""
    write_registry(os.path.join(tree, "projects"), SECRETS_REGISTRY)
    write_json(os.path.join(tree, "runtime", "hosts", "registry.json"), HOSTS_REGISTRY)


class code_tree:
    """The tree a reader takes as the checkout the code is in: each keeps it
    in a module global (new_agent, store_enroll, secrets_sync, adr; results
    and commit_class ask roots) or in roots. A fixture stands in for it, so a case reads no live file and
    still tells that tree from the one AGENT_FABRIC_ROOT names. Needs
    tools/fabric on sys.path."""
    def __init__(self, tree: str, *modules, attr: str = "ROOT"):
        self.tree, self.modules, self.attr = tree, modules, attr

    def __enter__(self):
        import roots
        self.saved = [(m, self.attr, getattr(m, self.attr)) for m in self.modules] + [(roots, "_CODE_ROOT", roots._CODE_ROOT)]
        for m, name, _ in self.saved:
            setattr(m, name, self.tree)

    def __exit__(self, *exc):
        for m, name, value in self.saved:
            setattr(m, name, value)


def write_operator_projects(operator: str, projects: dict[str, list[str]]) -> str:
    """An operator tree (AGENT_FABRIC_OPERATOR) whose projects/registry.json
    registers `projects`, each id with its remotes; the tree's path."""
    write_registry(os.path.join(operator, "projects"),
                   {"projects": {pid: {"remotes": remotes} for pid, remotes in projects.items()}})
    return operator


# ADR-045 §5 rule 2's instance data, as paths in a fabric tree: what a test
# that builds a fabric from the checkout (git archive HEAD) takes out before
# writing the fixtures its case needs. The roles (catalogue and roles as
# adapted) and the decision records go whole: rule 2 counts the
# organization's records as instance data, and until §6 splits them from
# the engine's, a test that needs one writes it.
INSTANCE_PATHS = ("projects/registry.json", "runtime/hosts/registry.json", "identities/roles",
                  "identities/keys", "identities/recovery.asc", "routing/profiles.json", "routing/policies",
                  "memory", "docs/live-checks", "docs/adr")


def strip_instance(tree: str) -> None:
    """Remove the instance data from a fabric tree: INSTANCE_PATHS,
    policies/*.json and each project's integration/."""
    for rel in INSTANCE_PATHS:
        p = os.path.join(tree, rel)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        elif os.path.lexists(p):
            os.remove(p)
    for f in os.listdir(os.path.join(tree, "policies")):
        if f.endswith(".json"):
            os.remove(os.path.join(tree, "policies", f))
    for proj in os.listdir(os.path.join(tree, "projects")):
        integration = os.path.join(tree, "projects", proj, "integration")
        if os.path.isdir(integration):
            shutil.rmtree(integration)


# A policies/auto-mode.json for a reader of the operator's policy
# (runtime/claude-code/user-settings.py, through tools/fabric/roots.py). The
# Organization text is in no live policy: a reader of the checkout's file
# writes another one.
AUTO_MODE_POLICY = {"environment": {"Organization": "the fixture operator"}, "allow": [], "soft_deny": [], "hard_deny": []}


def write_operator_policy(tmp: str, doc: dict = AUTO_MODE_POLICY) -> str:
    """<tmp>/operator/policies/auto-mode.json holding `doc`; the operator
    tree, for AGENT_FABRIC_OPERATOR."""
    operator = os.path.join(tmp, "operator")
    os.makedirs(os.path.join(operator, "policies"), exist_ok=True)
    with open(os.path.join(operator, "policies", "auto-mode.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return operator


# The operator half of routing (the profiles overlay and the review grade):
# the frozen copy in tests/fixtures/routing-distinct, roles and agents empty.
# A test that resolves routing takes the engine's files from the checkout
# and these from here.
ROUTING_OPERATOR_IGNORE = ("profiles.json", "policies")
_ROUTING_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "routing-distinct")


def write_routing_overlay(routing_dir: str) -> None:
    """Put the fixture profiles.json and policies/ into `routing_dir`, an
    engine routing directory copied with ROUTING_OPERATOR_IGNORE."""
    shutil.copy2(os.path.join(_ROUTING_FIXTURE, "profiles.json"), os.path.join(routing_dir, "profiles.json"))
    shutil.copytree(os.path.join(_ROUTING_FIXTURE, "policies"), os.path.join(routing_dir, "policies"))


def write_gzcoord_integrations(operator: str, projects: dict[str, tuple[str, str]]) -> str:
    """An operator tree (AGENT_FABRIC_OPERATOR) holding each project's
    projects/<id>/integration/gzcoord/config.json with its (relay_url,
    channel); the tree's path. The live ones are the operator's, absent from
    a checkout without its instance data."""
    for pid, (relay_url, channel) in projects.items():
        d = os.path.join(operator, "projects", pid, "integration", "gzcoord")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"relay_url": relay_url, "channel": channel}, fh)
    return operator
