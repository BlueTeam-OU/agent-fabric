"""tools/fabric/control/ops/memory.py — the drain over the control plane: the account's own memory, harvested by its own daemon.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import base64
import gzip
import hashlib
import os
import re
import subprocess
import sys
from typing import Any, Callable

from . import util

# THE DRAIN, over the control plane (the CEO, 2026-09-17: the way out of
# god mode). Until now a drain read another account's home through sudo
# (bin/fabric-host drain). Here the account's own daemon runs the
# harvester on its own memory — one bundle per memory directory Claude
# Code keeps for it (~/.claude/projects/<slug>/memory), each resolved to
# the working copy it belongs to by matching the slug against the
# account's ~/projects/* — and answers with the bundles gzipped and
# base64, in parts that fit the relay's 128 KiB message limit, plus each
# harvest report (`needs_rendering` and the skipped list included). No
# request field reaches argv: the op takes none. The harvester refuses
# the whole drain when a memory carries a credential by shape
# (harvest_memory.CREDENTIAL_PATTERNS), so no secret reaches the channel;
# a memory directory with no working copy beside it, or with two, is
# named and left where it is.
# The harness keeps an account's per-project memory in <slug>/memory under its own
# projects directory: the account's, not the operator's instance data (roots.py).
HARNESS_MEMORY = "memory"
MEMORY_PART_BYTES = 90 * 1024
GZIP_OS_BYTE, GZIP_OS_UNIX = 9, 3
HARVEST_TIMEOUT_S = 120
HARVEST_MAX_BYTES = 64 * 1024 * 1024
ERROR_TAIL = 400

_ALNUM = re.compile("[A-Za-z0-9]")


def memory_slug(directory: str) -> str:
    """The harness's name for a launch directory: every character that is not
    a letter or a digit becomes `-` — `/` and `.` alike (read back 2026-09-17:
    ~/projects/foo.bar is -home-…-projects-foo-bar). The harvester's
    memory_slug is the same rule. The harness counts UTF-16 units, so a
    character outside the Basic Multilingual Plane is two dashes."""
    return "".join(c if _ALNUM.fullmatch(c) else ("--" if ord(c) > 0xFFFF else "-")
                   for c in os.path.abspath(directory))


def memory_dirs(home: str | None = None, projects_dir: str | None = None, fabric: str | None = None) -> list[dict]:
    """A session started in ~/projects itself keeps its memory under the
    projects root's slug, which names no working copy: that workspace's
    CLAUDE.md is the fabric's, so its memory is filed under the account's
    fabric checkout, and the row says so (projects_root). Without a checkout
    there it stays a no-working-copy row: reported, never guessed.
    Listings are sorted, where the Node took the directory's order."""
    home = os.path.expanduser("~") if home is None else home
    projects_dir = os.path.join(home, "projects") if projects_dir is None else projects_dir
    fabric = os.path.join(projects_dir, "agent-fabric") if fabric is None else fabric
    root = os.path.join(home, ".claude", "projects")
    try:
        slugs = sorted(os.listdir(root))
    except OSError:
        return []
    try:
        copies = [d for d in (os.path.join(projects_dir, n) for n in sorted(os.listdir(projects_dir))) if os.path.isdir(d)]
    except OSError:
        copies = []   # no projects dir
    by_slug: dict[str, str] = {}
    ambiguous: set[str] = set()
    for d in copies:
        k = memory_slug(d)
        if k in by_slug:
            ambiguous.add(k)
        else:
            by_slug[k] = d
    root_slug = memory_slug(projects_dir)
    fabric_here = os.path.isdir(fabric)
    out: list[dict] = []
    for slug in slugs:
        memory = os.path.join(root, slug, HARNESS_MEMORY)
        try:
            n = len([f for f in os.listdir(memory) if f.endswith(".md") and f != "MEMORY.md"])
        except OSError:
            continue
        if not n:
            continue
        # Two working copies with one slug (foo.bar and foo-bar): the
        # harness cannot tell them apart and neither can this; named, not guessed.
        if slug == root_slug and fabric_here:
            out.append({"slug": slug, "memory": memory, "files": n, "working_copy": fabric, "projects_root": True})
            continue
        row: dict[str, Any] = {"slug": slug, "memory": memory, "files": n,
                               "working_copy": None if slug in ambiguous else by_slug.get(slug)}
        if slug in ambiguous:
            row["ambiguous"] = True
        out.append(row)
    return out


def memory(home: str | None = None, root: str | None = None, run: Callable[..., Any] = util.run_bounded,
           dirs: list[dict] | None = None, all: bool = False,  # noqa: A002 — the op's own word
           part_bytes: int = MEMORY_PART_BYTES) -> dict:
    home = os.path.expanduser("~") if home is None else home
    if root is None:
        root = os.environ.get("AGENT_FABRIC_ROOT")
        if root is None:
            root = os.path.join(home, "projects", "agent-fabric")
    if dirs is None:
        dirs = memory_dirs(home, os.path.join(home, "projects"), root)
    tool = os.path.join(root, "tools", "fabric", "harvest_memory.py")
    bundles: list[dict] = []
    for d in dirs:
        if not d.get("working_copy"):
            bundles.append({"slug": d["slug"], "files": d["files"],
                            "status": "ambiguous-working-copy" if d.get("ambiguous") else "no-working-copy"})
            continue
        where = {"slug": d["slug"], "files": d["files"], "working_copy": d["working_copy"],
                 **({"projects_root": True} if d.get("projects_root") else {})}
        # The tar on stdout, the report on stderr: one run gives both.
        # The projects root's store files under the fabric checkout beside the
        # checkout's own: named apart, so the two never share a watermark.
        args = [sys.executable, tool, "--bundle", "-", "--memory", d["memory"], "--working-copy", d["working_copy"],
                *(["--store", "projects-root"] if d.get("projects_root") else []), *(["--all"] if all else [])]
        try:
            r = run(args, timeout=HARVEST_TIMEOUT_S, max_bytes=HARVEST_MAX_BYTES,
                    env={**os.environ, "AGENT_FABRIC_ROOT": root})
        except (subprocess.SubprocessError, OSError) as e:
            # The harvester's own words when it said any; a timeout or a
            # missing interpreter says none, and is named instead of "".
            said = util.decode(getattr(e, "stderr", None)) or str(e)
            bundles.append({**where, "status": "harvest-failed", "error": said[-ERROR_TAIL:]})
            continue
        tar = bytes(r.stdout or b"")
        # zlib.gzipSync writes OS = 3 (Unix) where gzip.compress writes 255
        # (unknown); the reply is the same bytes from either daemon.
        gz = bytearray(gzip.compress(tar, compresslevel=9, mtime=0))
        gz[GZIP_OS_BYTE] = GZIP_OS_UNIX
        gz = bytes(gz)
        b64 = base64.b64encode(gz).decode("ascii")
        parts = [b64[i:i + part_bytes] for i in range(0, len(b64), part_bytes)]
        bundles.append({**where, "status": "ok", "bytes": len(tar), "gzip_bytes": len(gz),
                        "sha256": hashlib.sha256(tar).hexdigest(), "parts": len(parts),
                        "report": _report(util.decode(r.stderr)), "_parts": parts})
    return {"status": "ok", "bundles": bundles}


def _report(stderr: str) -> dict | None:
    try:
        j = util.loads(stderr)
    except ValueError:
        return None
    if not isinstance(j, dict):
        return None
    out: dict[str, Any] = {k: j[k] for k in ("claims", "counts") if k in j}   # absent: undefined, which JSON left out
    out["needs_rendering"] = j["needs_rendering"] if j.get("needs_rendering") is not None else []
    out["skipped_no_roles_class"] = j["skipped_no_roles_class"] if j.get("skipped_no_roles_class") is not None else []
    return out
