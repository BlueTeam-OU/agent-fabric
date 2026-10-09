#!/usr/bin/env python3
"""tools/fabric/workingcopy.py — working copy and logical project resolution.

A WORKING COPY is a filesystem checkout: a path, a git toplevel, a remote.
A PROJECT is the logical system that checkout is a copy of. Many working
copies map to one project (the legacy repository's clone directories were
all copies of one project), and neither of them is the agent using it.

Resolution is by the checkout's origin remote against projects/registry.json,
or by a `.agent-fabric-project` marker file at the toplevel naming the
project id — and a marker that names an unknown project is an error, not
a fall-through. A directory basename is never used to guess a project:
names are conveniences, and the old system's `legacy-family` bucket is
what guessing from them produced.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
MARKER = ".agent-fabric-project"


# A git that hangs (a stalled filesystem, a lock held elsewhere) must not
# hold a session start or a control-plane scan: a timeout falls into the
# SubprocessError clause and reads as "not a repository" (python-dev-03,
# from the review of #126's tools-install scan).
GIT_TIMEOUT_S = 30


def _git(args: list[str], cwd: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                             timeout=GIT_TIMEOUT_S).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.strip() or None


def toplevel(path: str) -> str | None:
    """The git toplevel containing `path`, or None outside any repository."""
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    if not os.path.isdir(directory):
        return None
    return _git(["rev-parse", "--show-toplevel"], directory)


def remote_url(top: str, name: str = "origin") -> str | None:
    return _git(["remote", "get-url", name], top)


# The two shapes git itself accepts for a remote (git-fetch(1), "GIT URLS"):
# a URL with a scheme, and the scp-like `[user@]host:path` — which git only
# reads as such when no slash precedes the first colon. Anything else (a
# local path, `file://`, a bare word) is not a remote this fabric matches.
_URL_RE = re.compile(
    r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?:(?P<user>[^@/]+)@)?"
    r"(?P<host>\[[^\]]+\]|[^:/\[\]]+)(?::(?P<port>\d+))?(?P<path>/.*)?$", re.I)
_SCP_RE = re.compile(r"^(?:(?P<user>[^@/]+)@)?(?P<host>\[[^\]]+\]|[^:/\[\]]+):(?P<path>.+)$")
_BARE_RE = re.compile(r"^(?P<host>[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?P<path>/.+)$", re.I)   # `github.com/org/repo`, the registry's shorthand: a hostname, then the path
_DEFAULT_PORT = {"ssh": 22, "git+ssh": 22, "ssh+git": 22, "https": 443, "http": 80, "git": 9418}
# Hosts whose repository paths are case-insensitive, so `Org/Repo` and
# `org/repo` are one repository there. Everywhere else the path is kept as
# written: a self-hosted forge may well tell them apart.
CASE_INSENSITIVE_PATH_HOSTS = frozenset({"github.com", "gitlab.com", "bitbucket.org"})


def parse_remote(url: str) -> dict[str, Any] | None:
    """{scheme, user, host, port, path} for a git remote, or None when the
    string is not a network remote (a local path, a bare word). `host` is
    lowercased (DNS is case-insensitive) and keeps IPv6 brackets; `port`
    is None when it is the scheme's default; `path` has its leading slash,
    a trailing slash and a trailing `.git` removed and its case KEPT."""
    u = url.strip()
    if "://" in u:
        m = _URL_RE.match(u)
        if not m or m.group("scheme").lower() == "file":
            return None                      # file:// and any URL without a host are local
        scheme = m.group("scheme").lower()
    elif "/" not in u.split(":", 1)[0] and ":" in u:
        m = _SCP_RE.fullmatch(u)                 # git's rule: scp-like only when no slash precedes the first colon
        if not m:
            return None
        scheme = "ssh"
    else:
        m = _BARE_RE.match(u)
        if not m:
            return None
        scheme = None
    host = m.group("host").lower()
    port = int(m.group("port")) if "port" in m.groupdict() and m.group("port") else None
    if scheme and port == _DEFAULT_PORT.get(scheme):
        port = None
    path = (m.group("path") or "").strip("/")
    if path.endswith(".git"):
        path = path[:-4].rstrip("/")
    if not host or not path:
        return None
    return {"scheme": scheme, "user": m.group("user") if "user" in m.groupdict() else None,
            "host": host, "port": port, "path": path}


def canonical_remote(url: str) -> str | None:
    """The repository a remote names, as one comparable string: host, a
    non-default port, and the path — the path lowercased only on hosts
    that treat it so (CASE_INSENSITIVE_PATH_HOSTS). Scheme and user are
    not part of it: `git@github.com:org/repo.git` and
    `https://github.com/org/repo` are one repository."""
    r = parse_remote(url)
    if r is None:
        return None
    path = r["path"].lower() if r["host"] in CASE_INSENSITIVE_PATH_HOSTS else r["path"]
    return f"{r['host']}{':' + str(r['port']) if r['port'] else ''}/{path}"


def normalize_remote(url: str) -> str:
    """Kept for callers that want a string for any input: canonical_remote,
    or the trimmed input when it is not a remote at all."""
    return canonical_remote(url) or url.strip()


def load_registry(path: str | None = None) -> dict[str, Any]:
    path = path or roots.projects_registry(engine=FABRIC_ROOT)
    if not os.path.exists(path):
        return {"version": 1, "projects": {}}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def project_for_remote(url: str | None, registry: dict[str, Any]) -> str | None:
    wanted = canonical_remote(url) if url else None
    if not wanted:
        return None
    for pid, entry in (registry.get("projects") or {}).items():
        if any(canonical_remote(r) == wanted for r in entry.get("remotes") or []):
            return pid
    return None


def resolve(path: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """{path, id, remote, project, project_source} for the working copy
    containing `path`. Outside a repository every field is None."""
    top = toplevel(path)
    if not top:
        return {"path": None, "id": None, "remote": None, "project": None, "project_source": None}
    registry = registry if registry is not None else load_registry()
    remote = remote_url(top)
    project, source = None, None
    marker = os.path.join(top, MARKER)
    if os.path.isfile(marker):
        # A marker is a declaration, not a hint: one that names nothing the
        # registry knows is an error the human sees, never a silent fall
        # back to the remote (review, 2026-09-16 — before this, a typo in
        # the marker resolved to whatever the remote said, or to nothing).
        with open(marker, encoding="utf-8") as fh:
            declared = fh.read().strip()
        known = registry.get("projects") or {}
        if not declared:
            raise SystemExit(f"workingcopy: {marker} is empty; it must name a project id from "
                             f"projects/registry.json ({', '.join(sorted(known)) or 'none registered'}), "
                             "or be removed so the remote decides")
        if declared not in known:
            raise SystemExit(f"workingcopy: {marker} names project {declared!r}, which projects/registry.json "
                             f"does not know ({', '.join(sorted(known)) or 'none registered'}). Fix the marker, "
                             "register the project, or remove the marker so the remote decides")
        project, source = declared, "marker"
    if project is None:
        project = project_for_remote(remote, registry)
        source = "remote" if project else None
    return {"path": top, "id": os.path.basename(top), "remote": remote,
            "project": project, "project_source": source}


if __name__ == "__main__":
    import sys
    print(json.dumps(resolve(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()), indent=2, sort_keys=True))

def sibling_working_copies(root: str, fabric_project_id: str = "agent-fabric") -> dict[str, str]:
    """Registered projects whose working copy sits beside this checkout
    (the workspace layout: projects/<clone>/ for each), with a
    .agent-fabric/memory/ to lint. Keyed by project id. Shared by lint
    and the assembler (2026-09-18): what sits beside the fabric is what
    every fabric run must see, the hygiene lists included."""
    out: dict[str, str] = {}
    parent = os.path.dirname(os.path.abspath(root))
    registry = load_registry(roots.projects_registry(engine=root))
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return out
    for name in names:
        path = os.path.join(parent, name)
        # The project's own tree, never the operator's corpus: roots does not
        # resolve it, and an operator's move must not move it.
        if path == os.path.abspath(root) or not os.path.isdir(os.path.join(path, ".agent-fabric", "memory")):
            continue
        pid = resolve(path, registry).get("project")
        if pid and pid != fabric_project_id and pid not in out:
            out[pid] = path
    return out
