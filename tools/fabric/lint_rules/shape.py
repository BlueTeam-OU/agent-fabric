"""tools/fabric/lint_rules/shape.py — the repository's shape: bash size, the host registry and the candidate roles.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .base import _git, _tracked, lint_environ, roots
from .schema import load_schema, validate_json


BASH_LINE_LIMIT = 150


BASH_SHEBANG = re.compile(r"^#!.*\b(bash|sh)\b")


def _is_bash(path: str) -> bool:
    if path.endswith(".sh"):
        return True
    try:
        with open(path, "rb") as fh:
            first = fh.readline(200).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(BASH_SHEBANG.match(first))


def bash_size_findings(root: str, base_ref: str = "origin/main") -> list[str]:
    """ADR-040 §5 rule 2: a tracked bash script over 150 lines must be on
    policies/bash-allowlist.json; an entry whose script is gone or back
    under the limit is stale; an entry the base branch's list does not
    have is an addition, and the list only shrinks. Without a readable
    base (a fresh clone, the commit that adds the list) additions are not
    judged."""
    listed_path = roots.policy("bash-allowlist.json", engine=root)
    try:
        listed = (json.load(open(listed_path, encoding="utf-8")).get("scripts") or {})
    except FileNotFoundError:
        listed = {}
    except ValueError as e:
        return [f"policies/bash-allowlist.json: not JSON ({e})"]
    findings = []
    over = {}
    for rel in _tracked(root):
        full = os.path.join(root, rel)
        if not os.path.isfile(full) or os.path.islink(full) or not _is_bash(full):
            continue
        with open(full, "rb") as fh:
            n = sum(1 for _ in fh)
        if n > BASH_LINE_LIMIT:
            over[rel] = n
    for rel, n in sorted(over.items()):
        if rel not in listed:
            findings.append(f"{rel}: {n} lines of bash, over {BASH_LINE_LIMIT} and not on policies/bash-allowlist.json — "
                            "write it in Python (ADR-040)")
    for rel in sorted(listed):
        if rel not in over:
            findings.append(f"policies/bash-allowlist.json: {rel} is gone or {BASH_LINE_LIMIT} lines or fewer — remove its entry")
    # The list as the branch forked from it, not as the base stands now: a
    # branch behind main still lists what main has since ported away, and
    # against main's tip those read as additions (review of #70). Without
    # a merge base (a ref with no common history) the ref itself.
    mb = _git().run(root, "merge-base", "HEAD", base_ref, check=False, timeout=60)
    since = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base_ref
    base = _git().run(root, "show", f"{since}:policies/bash-allowlist.json", check=False, timeout=60)
    if base.returncode == 0:
        try:
            before = set((json.loads(base.stdout).get("scripts") or {}))
        except ValueError:
            before = None
        if before is not None:
            for rel in sorted(set(listed) - before):
                findings.append(f"policies/bash-allowlist.json: {rel} is added; the list only shrinks (ADR-040 §5 rule 2)")
    return findings


def host_registry_findings(root: str) -> list[str]:
    """runtime/hosts/registry.json: a host id is its short hostname, so ids
    are unique by construction and an ssh destination reaches one host;
    exactly one host is the one this registry is read on (ssh null); a
    placement names a known host. Placement is where an account is, never
    who it is — the schema forbids anything else in a host entry."""
    findings: list[str] = []
    path = roots.hosts_registry(engine=root, environ=lint_environ())
    if not os.path.exists(path):
        return findings
    where = "runtime/hosts/registry.json"
    try:
        reg = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{where}: does not parse ({exc})"]
    schema = load_schema(root, os.path.join("runtime", "hosts", "schema"), "hosts")
    if schema:
        findings += validate_json(schema, reg, where)
        if findings:
            return findings
    hosts = reg.get("hosts") or {}
    local = [h for h, e in hosts.items() if e.get("ssh") is None]
    if len(local) != 1:
        findings.append(f"{where}: exactly one host has ssh null (the one this registry is read on); found {len(local)}: {', '.join(sorted(local)) or 'none'}")
    seen: dict[str, str] = {}
    for hid, e in sorted(hosts.items()):
        dest = e.get("ssh")
        if dest is None:
            continue
        if dest in seen:
            findings.append(f"{where}: hosts {seen[dest]} and {hid} share the ssh destination {dest!r}; one destination is one host")
        seen[dest] = hid
    placement = reg.get("placement") or {}
    for login, hid in sorted(placement.items()):
        if hid not in hosts:
            findings.append(f"{where}: placement of {login!r} names host {hid!r}, which is not registered")
    # A login's kind (ADR-044 §5 rule 1): human or agent, and only for a placed login.
    kinds = reg.get("kinds", {})
    if not isinstance(kinds, dict):
        findings.append(f"{where}: kinds is not an object of login -> kind")
        kinds = {}
    for login, kind in sorted(kinds.items()):
        if kind not in ("agent", "human"):
            findings.append(f"{where}: kinds[{login!r}] is {kind!r}; a kind is agent or human")
        if login not in placement:
            findings.append(f"{where}: kinds names {login!r}, which is not placed")
    return findings


def agentd_selector_findings(root: str) -> list[str]:
    """runtime/control/agentd.json (ADR-040 Wave 8, s7): bootstrap refuses an
    unsound selector at every account, so it is refused here first, where
    one commit can fix it; and a listed login that is placed nowhere is a
    cutover no account will ever run — a misspelling, or a login gone."""
    import agentd_unit  # tools/fabric, on the path lint.py set
    where = agentd_unit.SELECTOR_REL
    try:
        doc = json.load(open(os.path.join(root, where), encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        return [f"{where}: does not parse ({exc})"]
    findings = [f"{where}: {p}" for p in agentd_unit.problems(doc)]
    if findings:
        return findings
    # An unreadable registry is host_registry_findings'.
    try:
        placement = json.load(open(roots.hosts_registry(engine=root, environ=lint_environ()),
                                   encoding="utf-8")).get("placement") or {}
    except (OSError, ValueError, AttributeError):
        return findings
    for login in doc.get("python", []):
        if login not in placement:
            findings.append(f"{where}: python names {login!r}, which runtime/hosts/registry.json does not place")
    return findings


def candidate_role_findings(root: str, catalog: dict[str, Any] | None,
                            taxonomy_roles: dict[str, set[str]]) -> list[str]:
    """`candidate: true` in the catalogue means the role has not yet proved
    it carries its own weight. The proof is structural, not remembered
    (architect-cto's proposal, narrowed by the owner, 2026-09-18): a
    project's taxonomy binds the role AND a login named for it is placed
    on a host (runtime/hosts/registry.json). Such a role is not a
    candidate; the flag must go in the same change that made it true."""
    if not catalog:
        return []
    path = roots.hosts_registry(engine=root, environ=lint_environ())
    try:
        placement = (json.load(open(path, encoding="utf-8")).get("placement") or {})
    except (OSError, ValueError):
        return []
    bound: dict[str, list[str]] = {}
    for pid, roles in taxonomy_roles.items():
        for rid in roles:
            bound.setdefault(rid, []).append(pid)
    out: list[str] = []
    for r in catalog.get("roles", []) or []:
        if not isinstance(r, dict) or not r.get("candidate"):
            continue
        rid = r.get("id") or ""
        logins = sorted(l for l in placement if l == rid or l.startswith(rid + "-"))
        if rid in bound and logins:
            out.append(f"identities/roles/catalog.json: role {rid!r} is a candidate, yet "
                       f"{', '.join(sorted(bound[rid]))} binds it and {', '.join(logins)} holds it — "
                       "a proved role; drop `candidate`")
    return out
