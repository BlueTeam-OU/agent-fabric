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


# ADR-045 §5 rule 2's instance data, as paths in a fabric tree: what a test
# that builds a fabric from the checkout (git archive HEAD) takes out before
# writing the fixtures its case needs.
INSTANCE_PATHS = ("projects/registry.json", "runtime/hosts/registry.json", "identities/roles/catalog.json",
                  "identities/keys", "identities/recovery.asc", "routing/profiles.json", "routing/policies",
                  "memory", "docs/live-checks")


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
