"""tools/fabric/lint_rules/signing.py — policies/signing.json (agent-fabric ADR-057 §5 rules 1, 3, 5).
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os

from .base import workingcopy
from .schema import load_json, load_schema, validate_json

WHERE = "policies/signing.json"

# By path, as lint loads every module it trusts: a directory on sys.path
# would let a fixture fabric answer for the import.
_spec = importlib.util.spec_from_file_location(
    "fabric_signing_policy",
    os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "guards", "signing_policy.py"))
signing_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signing_policy)


def signing_findings(root: str, policy_path: str, registry_path: str) -> list[str]:
    """Its schema (the engine's, under `root`), then what a schema cannot
    say: every repository is the owner/name of one of a registered
    project's remotes, and no project is named twice (two entries for one
    repository under its old and new names would give it two formats and
    two cut-overs, and which one wins would be dict order). An absent file
    is not judged: the fleet default applies and nothing is refused."""
    if not os.path.exists(policy_path):
        return []
    findings: list[str] = []
    doc = load_json(policy_path, WHERE, findings)
    if doc is None:
        return findings
    schema = load_schema(root, os.path.join("identities", "schemas"), "signing")
    if schema:
        findings += validate_json(schema, doc, WHERE)
    # The readers' own check, so lint refuses whatever they would.
    findings += [f"{WHERE}: {p}" for p in signing_policy.shape_problems(doc)]
    if findings or not isinstance(doc.get("repositories"), dict):
        return sorted(set(findings))
    registry: dict = {}
    if os.path.exists(registry_path):
        registry = load_json(registry_path, "projects/registry.json", findings) or {}
    owner: dict[str, str] = {}
    for pid, entry in (registry.get("projects") or {}).items():
        for url in entry.get("remotes") or []:
            slug = signing_policy.slug_of(url, workingcopy.parse_remote)
            if slug:
                owner.setdefault(slug.lower(), pid)
    named: dict[str, str] = {}
    for slug in sorted(doc["repositories"]):
        pid = owner.get(slug.lower())
        if pid is None:
            findings.append(f"{WHERE}: {slug} is not the owner/name of any remote in projects/registry.json")
            continue
        if pid in named:
            findings.append(f"{WHERE}: {named[pid]} and {slug} both name project {pid}; one entry per repository")
            continue
        named[pid] = slug
    return findings
