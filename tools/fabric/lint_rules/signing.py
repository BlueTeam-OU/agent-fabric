"""tools/fabric/lint_rules/signing.py — policies/signing.json and policies/forge-keys/ (agent-fabric ADR-057 §5 rules 1, 3, 5, 8).
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile

from .base import workingcopy
from .schema import load_json, load_schema, validate_json

WHERE = "policies/signing.json"
GPG = "gpg"   # a name, so a test can stand in a host without it

# By path, as lint loads every module it trusts: a directory on sys.path
# would let a fixture fabric answer for the import.
_spec = importlib.util.spec_from_file_location(
    "fabric_signing_policy",
    os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "guards", "signing_policy.py"))
signing_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signing_policy)


def _own_since_findings(root: str, doc: dict, registry_path: str) -> list[str]:
    """The checker refuses a `since` that is not on the default branch; the
    repository lint runs in is held to the same, so a bad one is found when
    the policy is edited and not by the first red CI. No git repository, no
    origin the policy covers, a registry default_branch with no
    refs/remotes/origin/<it> in the clone, or a since this clone lacks: nothing
    said (the checker still refuses, with the whole clone in front of it)."""
    sink: list[str] = []
    try:
        remote = subprocess.run(["git", "-C", root, "config", "--get", "remote.origin.url"], capture_output=True,
                                text=True, timeout=30)
        registry = (load_json(registry_path, "projects/registry.json", sink) or {}) if os.path.exists(registry_path) else {}
        slug = signing_policy.slug_of(remote.stdout.strip(), workingcopy.parse_remote) if remote.returncode == 0 else None
        since = signing_policy.entry_for(doc, slug, registry, workingcopy.parse_remote)[1].get("since") if slug else None
        if not since:
            return []
        branch = None
        for entry in (registry.get("projects") or {}).values():
            slugs = [signing_policy.slug_of(u, workingcopy.parse_remote) for u in entry.get("remotes") or []]
            if slug.lower() in (x.lower() for x in slugs if x):
                branch = entry.get("default_branch")
                break
        base = f"refs/remotes/origin/{branch}" if branch else None
        # Never HEAD: a branch that carries its own since would pass. A tracking
        # ref that is missing is a clone to fetch; the checker still refuses.
        if base is None or subprocess.run(["git", "-C", root, "rev-parse", "-q", "--verify", f"{base}^{{commit}}"],
                                          capture_output=True, timeout=30).returncode != 0:
            return []
        rc = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", since, base], capture_output=True,
                            timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return []
    if rc == 1:
        return [f"{WHERE}: since {since} for {slug} is not an ancestor of {base}: it must be a commit on the default branch (or {base} is stale: fetch origin first)"]
    return []


def _forge_key_findings(policy_path: str, doc: dict) -> list[str]:
    """Each listed forge key has its file beside the policy, and that file is
    the key its fingerprint names (one primary, that one): the checker trusts
    what the file holds, so a file swapped for another key would admit that
    key's commits under the listed name. A file no entry lists is a finding
    too: a key that is committed and not listed looks trusted and is not."""
    listed = doc.get("forge_keys") or {}
    where = signing_policy.FORGE_KEYS_DIR
    folder = os.path.join(os.path.dirname(policy_path), where)
    try:
        present = sorted(n for n in os.listdir(folder) if n.endswith(".asc"))
    except OSError:
        present = []
    findings = [f"policies/{where}/{n}: no entry in forge_keys lists it" for n in present if n[:-4] not in listed]
    missing = [fpr for fpr in sorted(listed) if f"{fpr}.asc" not in present]
    findings += [f"{WHERE}: forge_keys lists {fpr} and policies/{where}/{fpr}.asc is not there" for fpr in missing]
    to_read = [fpr for fpr in sorted(listed) if fpr not in missing]
    if not to_read:
        return findings
    if not shutil.which(GPG):
        return findings + [f"policies/{where}/: gpg is not installed here, so no forge key's file could be checked"]
    home = tempfile.mkdtemp(prefix="forgekeys-")
    try:
        os.chmod(home, 0o700)
        for fpr in to_read:
            try:
                got = signing_policy.key_file_primaries(os.path.join(folder, f"{fpr}.asc"), home)
            except (OSError, subprocess.SubprocessError) as e:
                findings.append(f"policies/{where}/{fpr}.asc: gpg could not read it ({e})")
                continue
            if got != [fpr]:
                findings.append(f"policies/{where}/{fpr}.asc: holds {', '.join(got) or 'no key'}, "
                                f"not the one key {fpr} its name and forge_keys say")
    finally:
        try:
            subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
        shutil.rmtree(home, ignore_errors=True)
    return findings


def signing_findings(root: str, policy_path: str, registry_path: str) -> list[str]:
    """Its schema (the engine's, under `root`), then what a schema cannot
    say: every repository is the owner/name of one of a registered
    project's remotes, and no project is named twice (two entries for one
    repository under its old and new names would give it two formats and
    two cut-overs, and which one wins would be dict order). An absent file
    is not judged: the fleet default applies and nothing is refused. The
    forge keys are read beside `policy_path` (_forge_key_findings)."""
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
    findings += _forge_key_findings(policy_path, doc)
    findings += _own_since_findings(root, doc, registry_path)
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
