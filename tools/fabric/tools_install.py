#!/usr/bin/env python3
"""tools/fabric/tools_install.py — install a tool a project declares as an
account tool, into this account's ~/.local/bin, from the release the
registry pins (behind `fabric-tools --install <tool>`).

A tool in projects/registry.json with `"where": "account"` may carry

    "install": {"version": "3.69.0", "url": "https://…/doppler_3.69.0_linux_amd64.tar.gz",
                "sha256": "<64 hex>", "member": "doppler"}

`version` is what the tool's `proof` must print; `url` an https release
asset; `sha256` the asset's digest, checked before a byte of it is
unpacked or placed; `member`, when the asset is a .tar.gz, the one file in
it that is the tool (absent: the asset is the tool). Nothing is fetched
unless the registry says what it must hash to, and nothing is piped to a
shell.

The verdict, one per run:
  current    the tool's proof already prints the pinned version
  installed  fetched, hash verified, proved from its temporary file, then
             moved into ~/.local/bin in one rename
  skipped    this account has no working copy of a project that declares
             the tool (the Doppler CLI stays off every other account: the
             owner, 2026-10-08) — nothing was looked up, fetched or written
  failed     the fetch, the hash, the unpacking or the proof said no;
             whatever was already installed is untouched
  refused    the request names no installable tool, or the projects that
             declare it disagree about the pin

Exit codes (fabric-tools): 0 current, installed or skipped; 1 failed;
2 refused or a bad argument.
"""
from __future__ import annotations

import hashlib
import http.client
import io
import os
import re
import shlex
import signal
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from typing import Callable

import tools_check
import workingcopy

TOOL_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MEMBER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")  # a file name: no path, so no traversal
MAX_ASSET_BYTES = 128 * 1024 * 1024
FETCH_TIMEOUT_S = 120

Fetch = Callable[[str], bytes]


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """A release asset redirects to a CDN; it may not redirect off https.
    The hash would catch a swapped payload, but a downgrade is refused on
    sight rather than argued about."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError(f"redirect to a non-https address refused: {newurl[:80]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_https(url: str) -> bytes:
    opener = urllib.request.build_opener(_HttpsOnly)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "agent-fabric-tools-install"}),
                     timeout=FETCH_TIMEOUT_S) as r:
        body = r.read(MAX_ASSET_BYTES + 1)
    if len(body) > MAX_ASSET_BYTES:
        raise ValueError(f"the asset is over {MAX_ASSET_BYTES} bytes")
    return body


def declarations(reg: dict, tool: str) -> list[tuple[str, dict]]:
    """(project id, entry) for each project that lists `tool` as an account tool."""
    out = []
    for pid, project in sorted((reg.get("projects") or {}).items()):
        for entry in project.get("tools") or []:
            if entry.get("name") == tool and entry.get("where") == "account":
                out.append((pid, entry))
    return out


def working_copy_projects(projects_dir: str, reg: dict) -> set[str]:
    """The registry projects this account has a working copy of: the
    directories under ~/projects, each resolved as the rest of the fabric
    resolves one. A directory whose marker the registry does not know is
    not a working copy of anything here."""
    found: set[str] = set()
    try:
        names = sorted(os.listdir(projects_dir))
    except OSError:
        return found
    for name in names:
        path = os.path.join(projects_dir, name)
        if not os.path.isdir(path):
            continue
        try:
            pid = workingcopy.resolve(path, reg).get("project")
        except SystemExit:
            continue
        if pid:
            found.add(pid)
    return found


def check_pin(pin: object) -> str | None:
    """Why this `install` object cannot be acted on, or None."""
    if not isinstance(pin, dict):
        return "the registry gives the tool no install pin"
    version, url, digest, member = pin.get("version"), pin.get("url"), pin.get("sha256"), pin.get("member")
    if not isinstance(version, str) or not version.strip():
        return "the install pin has no version"
    if not isinstance(url, str) or not url.startswith("https://"):
        return "the install pin's url is not an https address"
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        return "the install pin's sha256 is not 64 lowercase hex digits"
    if member is not None and (not isinstance(member, str) or not MEMBER.fullmatch(member)):
        return "the install pin's member is not a plain file name"
    extra = sorted(set(pin) - {"version", "url", "sha256", "member"})
    if extra:
        return f"the install pin has fields this installer does not know: {', '.join(extra)}"
    return None


def prints_version(first_line: str, version: str) -> bool:
    # No "-" after the version either: 3.69.0-rc1 is not the pinned 3.69.0.
    return re.search(r"(?<![\w.])v?" + re.escape(version) + r"(?![\w.-])", first_line) is not None


def unpack(body: bytes, member: str | None) -> bytes:
    if member is None:
        return body
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
            info = tar.getmember(member)
            if not info.isreg():
                raise ValueError(f"{member} in the archive is not a regular file")
            if info.size > MAX_ASSET_BYTES:
                raise ValueError(f"{member} in the archive is over {MAX_ASSET_BYTES} bytes")
            fh = tar.extractfile(info)
            if fh is None:
                raise ValueError(f"{member} in the archive cannot be read")
            return fh.read()
    except KeyError:
        raise ValueError(f"the archive holds no {member}") from None
    except tarfile.TarError as e:
        raise ValueError(f"the asset is not a readable .tar.gz ({e})") from None


def exit_on_sigterm() -> None:
    """SIGTERM ends the run through `finally`, so the bound the control agent
    puts on it (or a stopped unit) leaves no executable temporary behind;
    Python's default would exit without running it."""
    def stop(signum: int, frame: object) -> None:
        sys.exit(128 + signum)
    signal.signal(signal.SIGTERM, stop)


def sweep_temporaries(bindir: str, tool: str) -> None:
    """Remove the temporaries of runs that were killed outright (SIGKILL):
    `.<tool>.<pid>.tmp` whose pid is no longer a process. A live pid's is
    another run's, in flight, and stays."""
    try:
        names = os.listdir(bindir)
    except OSError:
        return
    for name in names:
        m = re.fullmatch(r"\." + re.escape(tool) + r"\.(\d+)\.tmp", name)
        if not m:
            continue
        try:
            os.kill(int(m.group(1)), 0)
            continue
        except ProcessLookupError:
            pass
        except OSError:
            continue  # exists, or not ours to signal: not stale
        try:
            os.unlink(os.path.join(bindir, name))
        except OSError:
            pass


def prove_file(proof: str, tool: str, path: str) -> tuple[str, str]:
    """tools_check.prove for the file at `path`, whatever PATH says."""
    try:
        argv = shlex.split(proof)
    except ValueError as e:
        return "failed", f"proof is not a command line ({e})"
    if not argv or argv[0] != tool:
        return "failed", f"the proof does not run {tool}, so the new file cannot be proved before it is placed"
    return tools_check.prove(shlex.join([path, *argv[1:]]))


def install(tool: str, *, reg: dict, home: str, projects_dir: str | None = None,
            fetch: Fetch = fetch_https) -> dict:
    if not TOOL_NAME.fullmatch(tool or ""):
        return {"status": "refused", "tool": tool, "reason": "not a tool name"}
    declared = declarations(reg, tool)
    if not declared:
        return {"status": "refused", "tool": tool, "reason": "no project declares it as an account tool"}
    mine = working_copy_projects(projects_dir or os.path.join(home, "projects"), reg)
    wanted = [(pid, e) for pid, e in declared if pid in mine]
    if not wanted:
        return {"status": "skipped", "tool": tool,
                "reason": f"no working copy of {', '.join(pid for pid, _ in declared)} on this account"}
    for pid, e in wanted:
        bad = check_pin(e.get("install"))
        if bad:
            return {"status": "refused", "tool": tool, "reason": f"{pid}: {bad}"}
    if len({repr((sorted(e["install"].items()), e.get("proof"))) for _, e in wanted}) != 1:
        return {"status": "refused", "tool": tool,
                "reason": f"{', '.join(pid for pid, _ in wanted)} pin different installs or proofs of it"}
    entry = wanted[0][1]
    pin = entry["install"]
    version = pin["version"]
    status, found = tools_check.prove(entry["proof"])
    if status == "ok" and prints_version(found, version):
        return {"status": "current", "tool": tool, "version": version, "found": found}
    try:
        body = fetch(pin["url"])
    except (OSError, ValueError, http.client.HTTPException) as e:
        return {"status": "failed", "tool": tool, "reason": f"fetch: {getattr(e, 'reason', None) or e!r}"}
    if hashlib.sha256(body).hexdigest() != pin["sha256"]:
        return {"status": "failed", "tool": tool, "reason": "the asset's sha256 is not the pinned one; nothing was unpacked or placed"}
    try:
        payload = unpack(body, pin.get("member"))
    except ValueError as e:
        return {"status": "failed", "tool": tool, "reason": str(e)}
    bindir = os.path.join(home, ".local", "bin")
    target = os.path.join(bindir, tool)
    tmp = os.path.join(bindir, f".{tool}.{os.getpid()}.tmp")
    try:
        os.makedirs(bindir, mode=0o755, exist_ok=True)
        sweep_temporaries(bindir, tool)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o755)
        proved, said = prove_file(entry["proof"], tool, tmp)
        if proved != "ok" or not prints_version(said, version):
            why = said if proved != "ok" else f"it prints {said!r}, not {version}"
            return {"status": "failed", "tool": tool, "reason": f"the new file does not prove as {version}: {why}"}
        os.replace(tmp, target)
        tmp = ""
    except OSError as e:
        return {"status": "failed", "tool": tool, "reason": f"{target}: {e.strerror or e}"}
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return {"status": "installed", "tool": tool, "version": version, "path": target}
