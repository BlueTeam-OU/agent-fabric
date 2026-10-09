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


def write_registry(directory: str, doc: dict = ADR_REGISTRY) -> str:
    """<directory>/registry.json holding `doc`; its path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "registry.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


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
