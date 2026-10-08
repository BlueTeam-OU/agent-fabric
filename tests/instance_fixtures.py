"""Instance data a test builds for itself, never the checkout's live files
(agent-fabric ADR-045 §5 rules 2-3): what more than one test needs, kept in
one place. Each fixture holds only what its readers read."""
from __future__ import annotations

import json
import os

# The project ids tools/fabric/adr.py reads from projects/registry.json, to
# tell another project's cited ADR ("gzapp's ADR-075") from this one's. The
# decision records name gzapp alone; a record that comes to cite another
# project fails the clean-corpus cases ("cites ADR-NNN, which does not
# exist") until its id is added here.
ADR_REGISTRY = {"projects": {"agent-fabric": {}, "gzapp": {}}}


def write_registry(directory: str, doc: dict = ADR_REGISTRY) -> str:
    """<directory>/registry.json holding `doc`; its path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "registry.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path
