"""tools/fabric/lint_rules/shape.py — the repository's shape: bash size, the host registry and the candidate roles.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .base import _git, _tracked, lint_environ, roots
from .schema import load_schema, validate_json


# Retired by ADR-040 A 2026-10-11 ("the 150-line threshold is gone"); kept for the
# importers that still name it.
BASH_LINE_LIMIT = 160


BASH_SHEBANG = re.compile(r"^#!.*\b(bash|sh)\b")


def _is_bash(path: str) -> bool:
    if path.endswith((".sh", ".bash")):
        return True
    try:
        with open(path, "rb") as fh:
            first = fh.readline(200).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(BASH_SHEBANG.match(first))


FORWARDER_CODE_LINES = 12
_LOOP = re.compile(r"(?:^|[;&|(]\s*)(?:for|while|until)\s")
_CASE = re.compile(r"(?:^|[;&|(]\s*)case\s")
SECTIONS = ("stays", "ports")


def forwarder_shape(path: str) -> tuple[bool, str]:
    """ADR-040 §5 rule 1's forwarder by its shape: at most 12 lines of code
    (comments, blank lines and the shebang not counted), no loop and no
    case. (True, "") or (False, what it has instead)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        code = [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]
    why = []
    if len(code) > FORWARDER_CODE_LINES:
        why.append(f"{len(code)} lines of code")
    if any(_LOOP.search(l) for l in code):
        why.append("a loop")
    if any(_CASE.search(l) for l in code):
        why.append("a case")
    return (not why, ", ".join(why))


def _sections(doc: dict) -> dict[str, dict]:
    return {s: (doc.get(s) or {}) if isinstance(doc.get(s) or {}, dict) else {} for s in SECTIONS}


def bash_shape_findings(root: str, base_ref: str = "origin/main") -> list[str]:
    """ADR-040 §5 rule 2 (A 2026-10-11): a tracked bash file (.sh, .bash, or
    a first line naming bash or sh) is either a forwarder by rule 1's shape
    or on policies/bash-allowlist.json: `stays`, the closed pre-Python list,
    each entry with its reason, whose every addition is a finding; or
    `ports`, the files not yet ported, each naming its batch, which only
    shrinks. An entry whose file is gone or no longer bash is stale; a
    `ports` entry whose file now has the forwarder's shape is ported.
    Additions are judged against the list as the branch forked from it; a
    base without the list, or without that section, judges none (the
    commit that introduces it)."""
    listed_path = roots.policy("bash-allowlist.json", engine=root)
    try:
        doc = json.load(open(listed_path, encoding="utf-8"))
    except FileNotFoundError:
        doc = {}
    except ValueError as e:
        return [f"policies/bash-allowlist.json: not JSON ({e})"]
    findings = []
    if "scripts" in doc:
        findings.append("policies/bash-allowlist.json: `scripts` is the retired 160-line list; the sections are "
                        "`stays` and `ports` (ADR-040 §5 rule 2)")
    sec = _sections(doc)
    for name, entries in sec.items():
        for rel, why in sorted(entries.items()):
            if not (isinstance(why, str) and why.strip()):
                findings.append(f"policies/bash-allowlist.json: {name} entry {rel} gives no "
                                f"{'reason' if name == 'stays' else 'batch'}")
    bash = {}
    for rel in _tracked(root):
        full = os.path.join(root, rel)
        if os.path.isfile(full) and not os.path.islink(full) and _is_bash(full):
            bash[rel] = forwarder_shape(full)
    for rel, (ok, why) in sorted(bash.items()):
        if ok or rel in sec["stays"] or rel in sec["ports"]:
            continue
        findings.append(f"{rel}: bash that is not a forwarder ({why}) and not on policies/bash-allowlist.json — "
                        f"write it in Python, or as a forwarder of at most {FORWARDER_CODE_LINES} lines of code with "
                        "no loop and no case (ADR-040 §5 rules 1, 2)")
    for name in SECTIONS:
        for rel in sorted(sec[name]):
            if rel not in bash:
                findings.append(f"policies/bash-allowlist.json: {name} entry {rel} is gone or not bash — remove it")
            elif name == "ports" and bash[rel][0]:
                findings.append(f"policies/bash-allowlist.json: {rel} has the forwarder's shape now — it is "
                                "ported; remove its ports entry")
    # The list as the branch forked from it, not as the base stands now: a
    # branch behind main still lists what main has since ported away, and
    # against main's tip those read as additions (review of #70). Without
    # a merge base (a ref with no common history) the ref itself.
    mb = _git().run(root, "merge-base", "HEAD", base_ref, check=False, timeout=60)
    since = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base_ref
    base = _git().run(root, "show", f"{since}:policies/bash-allowlist.json", check=False, timeout=60)
    if base.returncode == 0:
        try:
            before_doc = json.loads(base.stdout)
        except ValueError:
            before_doc = None
        if isinstance(before_doc, dict):
            for name in SECTIONS:
                if name not in before_doc:
                    continue
                before = set(_sections(before_doc)[name])
                for rel in sorted(set(sec[name]) - before):
                    rule = ("the pre-Python list is closed" if name == "stays" else "the ports list only shrinks")
                    findings.append(f"policies/bash-allowlist.json: {name} entry {rel} is added; {rule} "
                                    "(ADR-040 §5 rule 2)")
    return findings


# The name lint.py and older callers import (ADR-040's first, 160-line form).
bash_size_findings = bash_shape_findings


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
    # Two hosts pinned at one sshd address would put two hosts' keys on one
    # known_hosts pattern, and ssh would accept either for both (ADR-048).
    at: dict[str, str] = {}
    for hid, e in sorted(hosts.items()):
        sshd = e.get("sshd")
        if not isinstance(sshd, dict):
            continue
        addr = f"{sshd.get('address')}:{sshd.get('port')}"
        if addr in at:
            findings.append(f"{where}: hosts {at[addr]} and {hid} share the sshd address {addr}; one known_hosts pattern is one host")
        at[addr] = hid
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


def agentd_unit_findings(root: str) -> list[str]:
    """runtime/control/agent-fabric-agentd.service (ADR-040 Wave 8, s8):
    bootstrap installs it as it is on every account, so a file with no
    ExecStart, two, or one that does not run the control agent is refused
    here first, where one commit can fix it."""
    import agentd_unit  # tools/fabric, on the path lint.py set
    where = os.path.join("runtime", "control", "agent-fabric-agentd.service")
    try:
        text = open(os.path.join(root, where), encoding="utf-8").read()
    except FileNotFoundError:
        # Required, not optional: bootstrap exits 1 without the unit.
        return [f"{where}: is missing (bootstrap installs it on every account)"]
    except (OSError, ValueError) as exc:
        return [f"{where}: cannot be read ({exc})"]
    starts = [ln for ln in text.splitlines() if ln.startswith("ExecStart=")]
    if len(starts) != 1:
        return [f"{where}: has {len(starts)} ExecStart lines, not one"]
    if agentd_unit.implementation_of(text) != "python":
        return [f"{where}: ExecStart does not run tools/fabric/control/agentd.py ({starts[0][:80]})"]
    return []


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
