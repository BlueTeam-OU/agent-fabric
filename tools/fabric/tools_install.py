#!/usr/bin/env python3
"""tools/fabric/tools_install.py — install a tool a project declares as an
account tool, into this account's ~/.local/bin, from the release the
registry pins (behind `fabric-tools --install <tool>`).

A tool in projects/registry.json with `"where": "account"` may carry

    "install": {"version": "3.69.0", "url": "https://…/doppler_3.69.0_linux_amd64.tar.gz",
                "sha256": "<64 hex>", "member": "doppler"}

`version` is what the tool's `proof` must print; `url` an https release
asset; `sha256` the asset's digest, checked before a byte of it is
unpacked or placed; `member`, when the asset is an archive, the one file in
it that is the tool (absent: the asset is the tool). An archive is a .tar.xz when
the url's path ends in that, and a .tar.gz otherwise, as every member pin
was before xz was admitted; the bytes must be the declared format's, so a
url that names the wrong one fails the run, never a silent reread as the
other. Nothing is fetched
unless the registry says what it must hash to, and nothing is piped to a
shell.

A tool that is more than one file is pinned as a tree instead of a member.
The Codex CLI is one: for every tool call its executable spawns
bin/codex-code-mode-host beside its own resolved path, and it finds its
bundled rg (and bwrap, where the host has none) only through
codex-package.json beside bin/. Installed as one file it ran no command at
all and answered from the brief alone (2026-10-12).

    "install": {"version": "0.162.1", "url": "…", "sha256": "…",
                "root": "package/vendor/x86_64-unknown-linux-musl",
                "members": ["bin/codex", "bin/codex-code-mode-host", …],
                "entrypoint": "bin/codex"}

Exactly the listed `members` (paths under `root` in the archive, each a
regular file) are unpacked, keeping their layout, into
~/.local/lib/agent-fabric-tools/<tool>/<version>/; nothing else in the
archive is placed. The tree is staged beside that directory, proved by
running its `entrypoint`, renamed into place whole, and only then is
~/.local/bin/<tool> made a symlink to the entrypoint; the tool's other
versions are removed after the switch. A tree pin is current only when the
proof prints the version AND ~/.local/bin/<tool> resolves to the tree's
entrypoint with every member in place: a single-file install of the same
version is replaced, never kept as current.

A tree too large to list is pinned whole: `"whole": true` stands where
`members` stood, and everything under `root` is unpacked (Zig's compiler
needs its lib/ directory, thousands of files, beside it).

    "install": {"version": "0.16.0", "url": "…/zig-x86_64-linux-0.16.0.tar.xz",
                "sha256": "…", "root": "zig-x86_64-linux-0.16.0",
                "whole": true, "entrypoint": "zig"}

Entries outside `root` are not placed. The archive is refused whole for an
entry with an absolute path or a `..` part, and for anything under `root` that
is not a directory, a regular file or a symlink whose target resolves inside
the tree; a path never passes through a link; the file count and the unpacked
size are bounded. Setuid, setgid and group- or world-write bits are dropped.

The verdict, one per run:
  current    the tool's proof already prints the pinned version (a tree
             pin: and ~/.local/bin/<tool> resolves into its whole tree)
  installed  fetched, hash verified, proved from its temporary file (a
             tree: its staged tree), then moved into ~/.local/bin in one
             rename (a tree: renamed into its version's directory, then
             ~/.local/bin/<tool> switched to a link into it)
  skipped    this account has no working copy of a project that declares
             the tool (the Doppler CLI stays off every other account: the
             owner, 2026-10-08) — nothing was looked up, fetched or written
  failed     the fetch, the hash, the unpacking or the proof said no;
             whatever was already installed is untouched
  refused    the request names no installable tool, a declaring project's
             pin cannot be acted on, or the projects that declare it
             disagree about the pin or the proof

Exit codes (fabric-tools): 0 current, installed or skipped; 1 failed;
2 refused or a bad argument.
"""
from __future__ import annotations

import hashlib
import http.client
import io
import lzma
import os
import re
import shlex
import shutil
import signal
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Callable

import tools_check
import workingcopy

TOOL_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
# A relative path whose every part is a plain name: a release tarball may keep
# its binary one directory down, and no part can be "..", empty or absolute.
MEMBER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*")
# A tree pin's version names a directory, so it is one plain name.
VERSION_DIR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
PIN_FIELDS = {"version", "url", "sha256", "member"}
TREE_FIELDS = {"root", "members", "whole", "entrypoint"}
MAX_TREE_MEMBERS = 64
# A whole tree has no list to bound it; Zig 0.16.0 is 20,832 entries and 358 MB.
MAX_TREE_ENTRIES = 50_000
# The url declares the format; these bytes must open the stream, or the url lied.
ARCHIVE_MAGIC = {"gz": b"\x1f\x8b", "xz": b"\xfd7zXZ\x00"}
# What reading a damaged stream raises, by format; all of it is "the asset is not a readable archive".
ARCHIVE_ERRORS = (tarfile.TarError, lzma.LZMAError, zlib.error, EOFError)
# Where a tree pin's tools live: a directory per tool, a directory per version under it.
TREES = os.path.join(".local", "lib", "agent-fabric-tools")
# Held in memory whole, so it is a bound on the account's memory, not on the tool: the pinned Codex CLI is a
# 158 MiB tarball around a 281 MiB binary (ADR-053 rule 7), which the earlier 128 MiB refused.
MAX_ASSET_BYTES = 512 * 1024 * 1024
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
        return "the install pin's member is not a relative path of plain names"
    extra = sorted(set(pin) - PIN_FIELDS - TREE_FIELDS)
    if extra:
        return f"the install pin has fields this installer does not know: {', '.join(extra)}"
    return check_tree(pin) if is_tree(pin) else None


def archive_format(url: str) -> str:
    """"xz" for a url path ending .tar.xz, else "gz": the pins that predate xz name no suffix
    consistently (a bare name, .tgz), and the magic check in open_tar fails a wrong declaration."""
    return "xz" if urllib.parse.urlsplit(url).path.endswith(".tar.xz") else "gz"


def open_tar(body: bytes, url: str) -> tarfile.TarFile:
    """The asset opened as the format its url declares; ValueError when the bytes are another."""
    fmt = archive_format(url)
    if not body.startswith(ARCHIVE_MAGIC[fmt]):
        raise ValueError(f"the asset is not {fmt} data, though its url names a {fmt} archive")
    return tarfile.open(fileobj=io.BytesIO(body), mode=f"r:{fmt}")


def is_tree(pin: dict) -> bool:
    return bool(TREE_FIELDS & set(pin))


def check_tree(pin: dict) -> str | None:
    """Why a tree pin (root, entrypoint, and members or whole) cannot be acted on, or None."""
    missing = sorted({"root", "entrypoint"} - set(pin))
    if missing:
        return f"the install pin's tree has no {', '.join(missing)}"
    if ("members" in pin) == ("whole" in pin):
        return "the install pin's tree lists its members or is whole, one of the two"
    if "whole" in pin and pin["whole"] is not True:
        return "the install pin's whole is not true"
    if "member" in pin:
        return "the install pin names both a member and a tree; it is one or the other"
    if not VERSION_DIR.fullmatch(pin["version"]):
        return "the install pin's version is not a plain directory name"
    root, members, entrypoint = pin["root"], pin.get("members"), pin["entrypoint"]
    if not isinstance(root, str) or not MEMBER.fullmatch(root):
        return "the install pin's root is not a relative path of plain names"
    if "whole" in pin:
        if not isinstance(entrypoint, str) or not MEMBER.fullmatch(entrypoint):
            return "the install pin's entrypoint is not a relative path of plain names"
        return None
    if (not isinstance(members, list) or not members or len(members) > MAX_TREE_MEMBERS
            or not all(isinstance(m, str) and MEMBER.fullmatch(m) for m in members)):
        return f"the install pin's members are not 1 to {MAX_TREE_MEMBERS} relative paths of plain names"
    if len(set(members)) != len(members):
        return "the install pin lists a member twice"
    # One member inside another would have to be a file and a directory at once.
    if any(b.startswith(a + "/") for a in members for b in members):
        return "the install pin lists a member inside another member"
    if entrypoint not in members:
        return "the install pin's entrypoint is not one of its members"
    return None


def prints_version(first_line: str, version: str) -> bool:
    # No "-" after the version either: 3.69.0-rc1 is not the pinned 3.69.0.
    return re.search(r"(?<![\w.])v?" + re.escape(version) + r"(?![\w.-])", first_line) is not None


def unpack(body: bytes, member: str | None, url: str) -> bytes:
    if member is None:
        return body
    try:
        with open_tar(body, url) as tar:
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
    except ARCHIVE_ERRORS as e:
        raise ValueError(f"the asset is not a readable archive ({e})") from None


class Terminated(BaseException):
    """SIGTERM, as an exception. Not SystemExit: the working-copy scan
    catches SystemExit from a bad marker and goes on, which would spend the
    one signal the control agent sends and let the run outlive its bound."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def exit_on_sigterm() -> None:
    """SIGTERM ends the run through `finally`, so the bound the control agent
    puts on it (or a stopped unit) leaves no executable temporary behind;
    Python's default would exit without running it. The caller turns
    Terminated into the exit status."""
    def stop(signum: int, frame: object) -> None:
        # One-shot: a later signal, inside the handler that turns this one
        # into an exit status or after it, would raise where nothing catches.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise Terminated(128 + signum)
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
        m = re.fullmatch(r"\." + re.escape(tool) + r"\.(\d{1,7})\.tmp", name)
        if not m or not _dead(int(m.group(1))):
            continue
        try:
            os.unlink(os.path.join(bindir, name))
        except OSError:
            pass


def _dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass  # exists, or not ours to signal: not stale
    return False


def sweep_trees(tooldir: str) -> None:
    """sweep_temporaries for a tree pin's directory: the staged `.<version>.<pid>.tmp`
    and set-aside `.<version>.<pid>.old` trees of runs that were killed outright."""
    try:
        names = os.listdir(tooldir)
    except OSError:
        return
    for name in names:
        m = re.fullmatch(r"\..+\.(\d{1,7})\.(tmp|old)", name)
        if m and _dead(int(m.group(1))):
            shutil.rmtree(os.path.join(tooldir, name), ignore_errors=True)


def tree_dir(home: str, tool: str, version: str) -> str:
    return os.path.join(home, TREES, tool, version)


def tree_in_place(home: str, tool: str, pin: dict) -> bool:
    """~/.local/bin/<tool> resolves to the pinned tree's entrypoint, and every member is a file there
    (a whole tree has no list: its entrypoint being a file there is all that is checked)."""
    tree = tree_dir(home, tool, pin["version"])
    link = os.path.join(home, ".local", "bin", tool)
    if os.path.realpath(link) != os.path.realpath(os.path.join(tree, pin["entrypoint"])):
        return False
    if pin.get("whole"):  # no list to check; the tree arrived by one rename, so its entrypoint is its mark
        return os.path.isfile(os.path.join(tree, pin["entrypoint"]))
    return all(os.path.isfile(p) and not os.path.islink(p) for p in (os.path.join(tree, m) for m in pin["members"]))


def unpack_tree(body: bytes, pin: dict, dest: str) -> None:
    """Exactly the pin's members, from under its root, into dest at their own
    relative paths; ValueError if one is absent, not a regular file, or the
    whole is past the size bound. Nothing else in the archive is read out.
    A whole-tree pin takes everything under its root instead."""
    if pin.get("whole"):
        return unpack_whole(body, pin, dest)
    total = 0
    try:
        with open_tar(body, pin["url"]) as tar:
            for m in pin["members"]:
                name = f"{pin['root']}/{m}"
                try:
                    info = tar.getmember(name)
                except KeyError:
                    raise ValueError(f"the archive holds no {name}") from None
                if not info.isreg():
                    raise ValueError(f"{name} in the archive is not a regular file")
                total += info.size
                if total > MAX_ASSET_BYTES:
                    raise ValueError(f"the tree's members are over {MAX_ASSET_BYTES} bytes")
                src = tar.extractfile(info)
                if src is None:
                    raise ValueError(f"{name} in the archive cannot be read")
                path = os.path.join(dest, m)
                os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    shutil.copyfileobj(src, fh, 1 << 20)
                    fh.flush()
                    os.fsync(fh.fileno())
                # The archive's execute bit, nothing more: no setuid, no group or world write.
                os.chmod(path, 0o755 if info.mode & 0o100 else 0o644)
    except ARCHIVE_ERRORS as e:
        raise ValueError(f"the asset is not a readable archive ({e})") from None


def unpack_whole(body: bytes, pin: dict, dest: str) -> None:
    """Everything under the pin's root into dest, ValueError at the first entry the module docstring
    refuses. Entries are written by hand, never extractall: each parent is walked one part at a time
    and a link in it ends the run, so no write can land outside dest however the archive orders its
    links and files."""
    prefix = pin["root"] + "/"
    real_dest = os.path.realpath(dest)
    entries = total = 0
    links: list[str] = []
    try:
        with open_tar(body, pin["url"]) as tar:
            for info in tar:
                name = info.name
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError(f"{name!r} in the archive is an absolute path or has a '..' part")
                if not name.startswith(prefix):
                    continue
                parts = name[len(prefix):].split("/")
                if any(p in ("", ".") or "\0" in p for p in parts):
                    raise ValueError(f"{name!r} in the archive is not a clean path")
                entries += 1
                if entries > MAX_TREE_ENTRIES:
                    raise ValueError(f"the tree holds over {MAX_TREE_ENTRIES} entries")
                path = _walk(real_dest, parts[:-1], name)
                path = os.path.join(path, parts[-1])
                if info.isdir():
                    if os.path.islink(path) or (os.path.lexists(path) and not os.path.isdir(path)):
                        raise ValueError(f"{name} in the archive is a directory over something else")
                    os.makedirs(path, mode=0o755, exist_ok=True)
                elif info.issym():
                    _check_link(info, real_dest, parts)
                    os.symlink(info.linkname, path)
                    links.append(path)
                elif info.isreg():
                    total += info.size
                    if total > MAX_ASSET_BYTES:
                        raise ValueError(f"the tree is over {MAX_ASSET_BYTES} bytes")
                    src = tar.extractfile(info)
                    if src is None:
                        raise ValueError(f"{name} in the archive cannot be read")
                    try:
                        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    except FileExistsError:
                        raise ValueError(f"{name} is in the archive twice") from None
                    with os.fdopen(fd, "wb") as fh:
                        shutil.copyfileobj(src, fh, 1 << 20)
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.chmod(path, 0o755 if info.mode & 0o100 else 0o644)
                else:
                    raise ValueError(f"{name} in the archive is neither a file, a directory nor a link")
    except ARCHIVE_ERRORS as e:
        raise ValueError(f"the asset is not a readable archive ({e})") from None
    # A chain of links can lead out where each one's own target looked inside, so what they resolve to is checked last.
    for link in links:
        resolved = os.path.realpath(link)
        if resolved != real_dest and not resolved.startswith(real_dest + os.sep):
            raise ValueError(f"{os.path.relpath(link, dest)} is a link that leaves the tree")
    if not os.path.isfile(os.path.join(dest, pin["entrypoint"])):
        raise ValueError(f"the archive holds no {pin['root']}/{pin['entrypoint']}")


def _walk(base: str, parts: list[str], name: str) -> str:
    """base joined with parts, each directory made if missing; ValueError if one is a link or not a directory."""
    cur = base
    for p in parts:
        cur = os.path.join(cur, p)
        if os.path.islink(cur):
            raise ValueError(f"{name} in the archive passes through a link")
        if not os.path.lexists(cur):
            os.mkdir(cur, 0o755)
        elif not os.path.isdir(cur):
            raise ValueError(f"{name} in the archive sits under a file")
    return cur


def _check_link(info: tarfile.TarInfo, real_dest: str, parts: list[str]) -> None:
    """The link's own target, resolved from where it sits, stays inside the tree (links it passes are rechecked at the end)."""
    target = info.linkname
    if target.startswith("/"):
        raise ValueError(f"{info.name} in the archive is a link to an absolute path")
    where = os.path.normpath(os.path.join(real_dest, *parts[:-1], target))
    if where != real_dest and not where.startswith(real_dest + os.sep):
        raise ValueError(f"{info.name} in the archive is a link that leaves the tree")


def install_tree(tool: str, entry: dict, body: bytes, home: str) -> dict:
    """A verified tree pin's asset, placed: staged, proved, renamed whole into
    its version's directory, then ~/.local/bin/<tool> switched to it. A
    failure at any step leaves the previous install as it was and nothing of
    this run behind."""
    pin = entry["install"]
    version = pin["version"]
    tooldir = os.path.join(home, TREES, tool)
    final = tree_dir(home, tool, version)
    stage = os.path.join(tooldir, f".{version}.{os.getpid()}.tmp")
    aside = os.path.join(tooldir, f".{version}.{os.getpid()}.old")
    bindir = os.path.join(home, ".local", "bin")
    target = os.path.join(bindir, tool)
    link_tmp = os.path.join(bindir, f".{tool}.{os.getpid()}.tmp")
    placed = moved = False
    try:
        os.makedirs(bindir, mode=0o755, exist_ok=True)
        os.makedirs(tooldir, mode=0o755, exist_ok=True)
        sweep_temporaries(bindir, tool)
        sweep_trees(tooldir)
        os.mkdir(stage, 0o755)
        try:
            unpack_tree(body, pin, stage)
        except ValueError as e:
            return {"status": "failed", "tool": tool, "reason": str(e)}
        proved, said = prove_file(entry["proof"], tool, os.path.join(stage, pin["entrypoint"]))
        if proved != "ok" or not prints_version(said, version):
            why = said if proved != "ok" else f"it prints {said!r}, not {version}"
            return {"status": "failed", "tool": tool, "reason": f"the new tree does not prove as {version}: {why}"}
        if os.path.lexists(final):
            os.rename(final, aside)
        os.rename(stage, final)
        stage, moved = "", True
        os.symlink(os.path.join(final, pin["entrypoint"]), link_tmp)
        os.replace(link_tmp, target)
        link_tmp = ""
        placed = True
    except OSError as e:
        # The second path, when there is one, is what was written to (a symlink's or a rename's destination).
        return {"status": "failed", "tool": tool, "reason": f"{e.filename2 or e.filename or target}: {e.strerror or e}"}
    finally:
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
        if link_tmp:
            try:
                os.unlink(link_tmp)
            except OSError:
                pass
        if moved and not placed:
            # The new tree took its version's place but the link never reached it: it goes, and the
            # previous tree (if any) is put back below, where the link still expects it (review of #229, F1).
            shutil.rmtree(final, ignore_errors=True)
        if os.path.lexists(aside):
            if placed:
                shutil.rmtree(aside, ignore_errors=True)
            else:
                try:
                    os.rename(aside, final)
                except OSError:
                    pass
        if not placed:
            for d in (tooldir, os.path.dirname(tooldir)):
                try:
                    os.rmdir(d)  # only if this run left it empty
                except OSError:
                    break
    # Other versions go only now that nothing links to them; a Codex still running from one loses its
    # helpers, and the review engine refuses a run whose tools failed rather than posting it.
    try:
        others = [n for n in os.listdir(tooldir) if n != version and not n.startswith(".")]
    except OSError:
        others = []
    for name in others:
        shutil.rmtree(os.path.join(tooldir, name), ignore_errors=True)
    return {"status": "installed", "tool": tool, "version": version, "path": target}


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
    if status == "ok" and prints_version(found, version) and (not is_tree(pin) or tree_in_place(home, tool, pin)):
        return {"status": "current", "tool": tool, "version": version, "found": found}
    try:
        body = fetch(pin["url"])
    except (OSError, ValueError, http.client.HTTPException) as e:
        reason = getattr(e, "reason", None)
        return {"status": "failed", "tool": tool, "reason": f"fetch: {reason if reason else repr(e)}"}
    if hashlib.sha256(body).hexdigest() != pin["sha256"]:
        return {"status": "failed", "tool": tool, "reason": "the asset's sha256 is not the pinned one; nothing was unpacked or placed"}
    if is_tree(pin):
        return install_tree(tool, entry, body, home)
    try:
        payload = unpack(body, pin.get("member"), pin["url"])
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
