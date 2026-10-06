"""tools/fabric/assembler/bundle.py — a drain bundle verified and unpacked.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import atexit
import json
import os
import hashlib
import sys
import shutil
import tarfile
import tempfile

from assembler.core import store_error


BUNDLE_FORMAT = "agent-fabric-drain/1"


def open_bundle(source: str) -> str:
    """Verify a drain bundle and unpack it into a temp directory; return
    the directory (its claims/ is --claims, itself --drain). Refuses, by
    file, anything the manifest does not vouch for."""
    # Every way a bundle can be unreadable or malformed is a refusal line
    # like the rest, never a traceback: a person reads it on the drain.
    try:
        stream = sys.stdin.buffer if source == "-" else open(source, "rb")
    except OSError as exc:
        sys.exit(f"assemble: bundle: {source} cannot be read ({exc.strerror or exc})")
    dest = tempfile.mkdtemp(prefix="assemble-bundle-")
    # The unpacked bundle lives for this run only; a refusal below exits
    # through sys.exit, so the removal is registered, not reached.
    atexit.register(shutil.rmtree, dest, ignore_errors=True)
    members: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=stream, mode="r|*") as tar:
            for info in tar:
                name = info.name
                if not info.isfile() or name.startswith(("/", "../")) or "/../" in name:
                    sys.exit(f"assemble: bundle: refusing member {name!r} (not a plain file under the bundle root)")
                fh = tar.extractfile(info)
                members[name] = fh.read() if fh else b""
    except (tarfile.TarError, EOFError, OSError) as exc:
        sys.exit(f"assemble: bundle: not a readable tar ({exc}) — not a drain bundle, or cut short")
    finally:
        if source != "-":
            stream.close()
    if "manifest.json" not in members:
        sys.exit("assemble: bundle: no manifest.json — not a drain bundle, or cut short before its first member")
    try:
        manifest = json.loads(members["manifest.json"])
    except ValueError as exc:
        sys.exit(f"assemble: bundle: manifest.json does not parse ({exc})")
    if not isinstance(manifest, dict):
        sys.exit("assemble: bundle: manifest.json is not an object")
    if manifest.get("format") != BUNDLE_FORMAT:
        sys.exit(f"assemble: bundle: format {manifest.get('format')!r}, expected {BUNDLE_FORMAT!r}")
    named = manifest.get("files") or {}
    if not isinstance(named, dict):
        sys.exit("assemble: bundle: manifest.json's files is not an object of name to digest")
    for f, digest in sorted(named.items()):
        if f not in members:
            sys.exit(f"assemble: bundle: {f} is named in the manifest but missing from the tar (cut short?)")
        actual = hashlib.sha256(members[f]).hexdigest()
        if actual != digest:
            sys.exit(f"assemble: bundle: {f} does not match its manifest digest (changed on the way, or a different harvest)")
    for f in sorted(members):
        if f != "manifest.json" and f not in named:
            sys.exit(f"assemble: bundle: {f} is in the tar but not in the manifest; nothing unnamed is read")
    if "harvest-report.json" not in members:
        sys.exit("assemble: bundle: no harvest-report.json")
    try:
        report = json.loads(members["harvest-report.json"])
    except ValueError as exc:
        sys.exit(f"assemble: bundle: harvest-report.json does not parse ({exc})")
    if not isinstance(report, dict):
        sys.exit("assemble: bundle: harvest-report.json is not an object")
    for key in ("agent", "host", "role", "project"):
        # agent and host name the store a watermark is kept for; role and
        # project may be null (an unregistered working copy), as before,
        # but the manifest says so rather than leaving them out.
        if key in ("agent", "host") and (not isinstance(manifest.get(key), str) or not manifest[key]):
            sys.exit(f"assemble: bundle: manifest.json names no {key}")
        if key not in manifest:
            sys.exit(f"assemble: bundle: manifest.json has no {key} field")
        if manifest.get(key) != report.get(key):
            sys.exit(f"assemble: bundle: manifest says {key}={manifest.get(key)!r} but harvest-report.json says {report.get(key)!r}")
    why = store_error(report)
    if why:
        sys.exit(f"assemble: bundle: {why}")
    for f, data in members.items():
        path = os.path.join(dest, f)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    print(f"bundle: {manifest['agent']}@{manifest['host']} role {manifest['role']} project {manifest['project']}: "
          f"{manifest.get('claims', '?')} claim(s), {len(named)} file(s) verified")
    return dest
