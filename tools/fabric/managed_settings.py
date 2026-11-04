#!/usr/bin/env python3
"""tools/fabric/managed_settings.py — each host's /etc/claude-code/managed-settings.json and the root-owned
snapshot of the guards it runs (agent-fabric ADR-043 rules 1 and 2).

    managed_settings.py render [--prefix P]                      the managed file for this host, on stdout
    managed_settings.py install --sha <40-hex> [--repo R]        (root) install the snapshot of that commit
    managed_settings.py check [--repo R] [--ref REF] [--json]    in force | missing | drifted | tampered | unreadable
    managed_settings.py probe                                    the live test (rule 6), as the login
    managed_settings.py restore                                  (root) the boot path: the kept file back to /etc

Run by the host's own /usr/bin/python3, as python_pin.py is (bin/fabric-managed), standard library only: the
installer cannot need what it installs.

WHAT ROOT RUNS. Root runs this file and git, and nothing else from the login's checkout. The snapshot is read
from the git object store with plumbing only (`cat-file --batch`, `ls-tree`), never `git archive` or a checkout:
both apply attribute filters and drivers from the repository's config, which the login writes, and would run
them as root. git runs under a config that names no hook, fsmonitor or transport, so nothing in the repository's
config runs a program and a missing object is never fetched. The store itself is the login's too, and git does
not re-hash an object it reads, so a planted loose object could answer for the operator's sha with other bytes:
every object, the commit, each tree and each blob, is hashed here and refused unless its content names it.
That is what makes the sha the operator names (`git ls-remote origin refs/heads/main`, not the checkout's own
view of main) exactly what is installed.

THE LAYOUT, under <prefix> (/usr/local/lib/agent-fabric, which survives a Qubes AppVM's reboot):
    managed/fabric-<sha>/        runtime/ tools/ routing/ policies/ projects/ identities/roles/ at <sha>, with a
                                 MANIFEST (the sha, then `<mode> <blob>\\t<path>` per file); root:root, files 0644
                                 (0755 where git says 100755), dirs 0755; compiled with checked-hash .pyc files
    managed/current              a link to fabric-<sha>, swapped by one os.replace: the only moment the guards change
    managed/managed-settings.json   the rendered file, kept for `restore` and the AppVM's boot script
A snapshot is built beside its final name and renamed into it, so a failure at any step leaves `current` on a
snapshot that runs. The previous snapshot is kept (a hook started a moment before the swap still reads it);
older ones are removed.

The overrides (AGENT_FABRIC_MANAGED_PREFIX, _ETC, _RC) are for a non-root test; as root they are ignored, as
python_pin.py ignores its own, whatever `sudo -E` carried in. Without root and without an override, install
and restore refuse.

exit 0 done (check: in force), 1 failed or not in force (one line), 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = "runtime/claude-code/managed/managed-settings.template.json"
ENTRY = "runtime/claude-code/managed/hook_entry.py"
PLACEHOLDER = "@ENTRY@"
# What the guards read: their scripts, the modules they import (tools/fabric/), routing/, the policies, the
# project registry, aliases.json and the role catalogue. A guard that comes to read outside these fails closed
# in the snapshot (a missing file), which is the signal to add its path here.
SNAPSHOT = ("runtime", "tools", "routing", "policies", "projects", "identities/roles")
MANIFEST = "MANIFEST"
FABRIC_PYTHON = "/usr/local/bin/fabric-python"
JQ_DIRS = ("/usr/bin", "/usr/local/bin")
GIT = "/usr/bin/git"
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
SNAP_NAME = re.compile(r"fabric-([0-9a-f]{40})", re.ASCII)

_AS_ROOT = os.geteuid() == 0
OVERRIDES = ("AGENT_FABRIC_MANAGED_PREFIX", "AGENT_FABRIC_MANAGED_ETC", "AGENT_FABRIC_MANAGED_RC")
PREFIX = "/usr/local/lib/agent-fabric" if _AS_ROOT else os.environ.get(OVERRIDES[0], "/usr/local/lib/agent-fabric")
ETC = "/etc/claude-code" if _AS_ROOT else os.environ.get(OVERRIDES[1], "/etc/claude-code")
RC = "/rw/config/rc.local.d/agent-fabric-managed.rc" if _AS_ROOT else os.environ.get(
    OVERRIDES[2], "/rw/config/rc.local.d/agent-fabric-managed.rc")
# The boot script writes the real /etc: it runs only as root, at boot, from /rw.
BOOT_ETC = "/etc/claude-code"

# Nothing of the caller's environment reaches git but what it needs to find itself: no global or system config,
# no replace refs, no lazy fetch of a missing object (a promisor remote would run a transport).
GIT_ENV = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "HOME": "/nonexistent", "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin",
           "LC_ALL": "C"}
GIT_CONFIG = ("-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
              # Root reads a repository the login owns; without this git refuses it as dubious. Command-line
              # config is the one place git honours it, for this call only.
              "-c", "safe.directory=*")


class Failed(Exception):
    """The whole answer, in one line."""


# --- render ----------------------------------------------------------------------------------------------------

def entry_path(prefix: str) -> str:
    return os.path.join(prefix, "managed", "current", ENTRY)


def render(template_text: str, prefix: str) -> str:
    """The managed file for a host whose snapshot lives under `prefix`: the template without its comment and every
    @ENTRY@ filled. Byte-stable (sorted keys, two-space indent, ASCII, one trailing newline): check compares bytes."""
    doc = json.loads(template_text)
    if not isinstance(doc, dict):
        raise Failed("the template is not a JSON object")
    doc.pop("_comment", None)
    entry = entry_path(prefix)

    def fill(v):
        if isinstance(v, str):
            return v.replace(PLACEHOLDER, entry)
        if isinstance(v, list):
            return [fill(x) for x in v]
        if isinstance(v, dict):
            return {k: fill(x) for k, x in v.items()}
        return v
    out = json.dumps(fill(doc), sort_keys=True, indent=2) + "\n"
    if PLACEHOLDER in out:
        raise Failed(f"{PLACEHOLDER} left in the rendered file (a key holds it)")
    return out


# --- git, read and verified ----------------------------------------------------------------------------------------

def _git(repo: str, *args: str, timeout: int = 60) -> bytes:
    try:
        r = subprocess.run([GIT, "--no-pager", *GIT_CONFIG, "-C", repo, *args], env=GIT_ENV,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Failed(f"git {args[0]} could not run: {e}") from None
    if r.returncode != 0:
        last = (r.stderr.decode("utf-8", "replace").strip().splitlines() or [f"exit {r.returncode}"])[-1]
        raise Failed(f"git {args[0]} failed: {last}")
    return r.stdout


def blob_id(data: bytes) -> str:
    """A file's git blob id: sha1 of `blob <len>\\0` and the content."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class Store:
    """One `git cat-file --batch`, every object it answers hashed against the name it was asked by."""

    def __init__(self, repo: str):
        try:
            self.p = subprocess.Popen([GIT, "--no-pager", *GIT_CONFIG, "-C", repo, "cat-file", "--batch"],
                                      env=GIT_ENV, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL)
        except OSError as e:
            raise Failed(f"git cat-file could not run: {e}") from None

    def read(self, oid: str, want: str) -> bytes:
        self.p.stdin.write(oid.encode() + b"\n")
        self.p.stdin.flush()
        head = self.p.stdout.readline().decode("ascii", "replace").split()
        if len(head) != 3 or head[0] != oid:
            raise Failed(f"object {oid} is not in the repository")
        kind, size = head[1], int(head[2])
        data = self.p.stdout.read(size)
        self.p.stdout.read(1)
        if kind != want:
            raise Failed(f"object {oid} is a {kind}, not a {want}")
        if len(data) != size or hashlib.sha1(b"%s %d\0" % (kind.encode(), size) + data).hexdigest() != oid:
            raise Failed(f"object {oid}'s content does not hash to its name: the object store was altered; "
                         "nothing installed")
        return data

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.p.kill()


def _tree_entries(data: bytes):
    i = 0
    while i < len(data):
        sp = data.index(b" ", i)
        nul = data.index(b"\0", sp)
        yield data[i:sp].decode("ascii"), data[sp + 1:nul], data[nul + 1:nul + 21].hex()
        i = nul + 21


def _safe_name(name: bytes) -> str:
    try:
        s = name.decode("utf-8")
    except UnicodeDecodeError:
        raise Failed(f"a path at the commit is not UTF-8 ({name!r})") from None
    if s in ("", ".", "..", ".git") or "/" in s or any(c in s for c in "\0\n\t\r"):
        raise Failed(f"a path at the commit has a name no snapshot may hold ({s!r})")
    return s


def snapshot_entries(repo: str, sha: str) -> list[tuple[str, str, str]]:
    """(mode, blob id, path) for every file under SNAPSHOT at commit `sha`, read through a verified walk from
    the commit object down, then checked against git's own `ls-tree` of the same paths."""
    if not SHA.fullmatch(sha):
        raise Failed(f"{sha!r} is not a 40-hex commit id")
    store = Store(repo)
    out: list[tuple[str, str, str]] = []
    try:
        commit = store.read(sha, "commit")
        first = commit.split(b"\n", 1)[0].split()
        if len(first) != 2 or first[0] != b"tree" or not SHA.fullmatch(first[1].decode("ascii", "replace")):
            raise Failed(f"commit {sha} names no tree")
        wanted = {tuple(p.split("/")) for p in SNAPSHOT}

        def walk(oid: str, at: tuple[str, ...]) -> None:
            for mode, raw, child in _tree_entries(store.read(oid, "tree")):
                name = _safe_name(raw)
                path = at + (name,)
                inside = any(path[:len(w)] == w for w in wanted)
                above = any(w[:len(path)] == path and len(w) > len(path) for w in wanted)
                if not (inside or above):
                    continue
                if mode == "40000":
                    walk(child, path)
                elif not inside:
                    continue
                elif mode in ("100644", "100755"):
                    out.append((mode, child, "/".join(path)))
                else:
                    raise Failed(f"{'/'.join(path)} at {sha} is a {'link' if mode == '120000' else 'submodule'} "
                                 f"(mode {mode}): a snapshot holds regular files only")
        walk(first[1].decode("ascii"), ())
    finally:
        store.close()
    out.sort(key=lambda e: e[2].encode())
    listed = _git(repo, "ls-tree", "-r", "-z", "--full-tree", sha, "--", *SNAPSHOT)
    theirs = []
    for rec in listed.split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1)
            mode, _kind, oid = meta.decode("ascii").split(" ")
            theirs.append((mode, oid, path.decode("utf-8", "surrogateescape")))
    theirs.sort(key=lambda e: e[2].encode("utf-8", "surrogateescape"))
    if theirs != out:
        raise Failed(f"git ls-tree and the verified walk of {sha} disagree; nothing installed")
    if not {TEMPLATE, ENTRY} <= {p for _m, _o, p in out}:
        raise Failed(f"commit {sha} carries no {TEMPLATE} or no {ENTRY}: it predates ADR-043's install")
    return out


def manifest_text(sha: str, entries: list[tuple[str, str, str]]) -> str:
    return f"sha {sha}\n" + "".join(f"{m} {o}\t{p}\n" for m, o, p in entries)


def parse_manifest(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    lines = text.split("\n")
    if not lines or not lines[0].startswith("sha ") or lines[-1] != "":
        raise ValueError("no sha line")
    sha = lines[0][4:]
    entries = []
    for line in lines[1:-1]:
        meta, path = line.split("\t", 1)
        mode, oid = meta.split(" ")
        entries.append((mode, oid, path))
    return sha, entries


# --- install -------------------------------------------------------------------------------------------------------

def _own(fd_or_path, root: bool) -> None:
    if root:
        if isinstance(fd_or_path, int):
            os.fchown(fd_or_path, 0, 0)
        else:
            os.chown(fd_or_path, 0, 0, follow_symlinks=False)


def _mkdir(path: str, root: bool) -> None:
    os.mkdir(path, 0o755)
    os.chmod(path, 0o755)
    _own(path, root)


def _write_new(path: str, data: bytes, mode: int, root: bool) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fchmod(fd, mode)
        _own(fd, root)
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_atomic(path: str, data: bytes, mode: int, root: bool) -> None:
    """`path` replaced in one rename by a file written beside it."""
    d = os.path.dirname(path)
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp-{os.urandom(6).hex()}")
    _write_new(tmp, data, mode, root)
    try:
        os.replace(tmp, path)
    except OSError:
        os.unlink(tmp)
        raise


def _point(link: str, target: str, root: bool) -> None:
    """`link` made to name `target` in one rename, never absent in between."""
    tmp = os.path.join(os.path.dirname(link), f".{os.path.basename(link)}-{os.urandom(6).hex()}")
    os.symlink(target, tmp)
    _own(tmp, root)
    os.replace(tmp, link)


def _ensure_dir(path: str, root: bool) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, 0o755, exist_ok=True)
    os.chmod(path, 0o755)
    _own(path, root)


def snapshot_problems(snap: str, sha: str, entries: list[tuple[str, str, str]] | None, owner: int) -> list[str]:
    """What is wrong with the snapshot at `snap` against its own MANIFEST (and `entries`, when given): an owner
    other than `owner`, anything group- or other-writable, a file whose content or mode is not its MANIFEST
    line's, a file the MANIFEST does not hold (a .pyc in __pycache__ aside), a MANIFEST of another sha."""
    problems: list[str] = []
    try:
        with open(os.path.join(snap, MANIFEST), encoding="utf-8") as f:
            text = f.read()
        msha, mentries = parse_manifest(text)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return [f"{snap}/{MANIFEST} unreadable: {e}"]
    if msha != sha:
        problems.append(f"{snap}/{MANIFEST} names {msha}, not {sha}")
    if entries is not None and mentries != entries:
        problems.append(f"{snap}/{MANIFEST} does not list the files of {sha}")
    listed = {p: (m, o) for m, o, p in mentries}
    seen = set()
    for d, dirs, files in os.walk(snap):
        for path in [d, *(os.path.join(d, n) for n in files), *(os.path.join(d, n) for n in dirs if
                                                                  os.path.islink(os.path.join(d, n)))]:
            st = os.lstat(path)
            if st.st_uid != owner:
                problems.append(f"{path} is owned by uid {st.st_uid}, not {owner}")
            if st.st_mode & 0o022:
                problems.append(f"{path} is group- or other-writable ({stat.filemode(st.st_mode)})")
            if stat.S_ISLNK(st.st_mode):
                problems.append(f"{path} is a link")
        for n in files:
            path = os.path.join(d, n)
            rel = os.path.relpath(path, snap)
            if rel == MANIFEST:
                continue
            if rel not in listed:
                if not (os.path.basename(d) == "__pycache__" and n.endswith(".pyc")):
                    problems.append(f"{rel}: in the snapshot, not in its MANIFEST")
                continue
            seen.add(rel)
            mode, oid = listed[rel]
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                continue
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as e:
                problems.append(f"{rel}: unreadable ({e})")
                continue
            if blob_id(data) != oid:
                problems.append(f"{rel}: content is not its MANIFEST blob {oid}")
            want = 0o755 if mode == "100755" else 0o644
            if stat.S_IMODE(st.st_mode) != want:
                problems.append(f"{rel}: mode {stat.S_IMODE(st.st_mode):o}, not {want:o}")
    for rel in sorted(set(listed) - seen):
        problems.append(f"{rel}: in the MANIFEST, not in the snapshot")
    return problems


def _compile(tree: str, final: str, root: bool) -> str:
    """The snapshot's modules compiled by the interpreter that runs them, as checked-hash .pyc files: a .pyc is
    used only while it matches its source's hash, so one that does not match is never what runs. The paths
    recorded are the final name's."""
    if not os.access(FABRIC_PYTHON, os.X_OK):
        return f"not compiled: {FABRIC_PYTHON} is absent (the guards then compile in memory)"
    try:
        r = subprocess.run([FABRIC_PYTHON, "-I", "-S", "-m", "compileall", "-q", "--invalidation-mode",
                            "checked-hash", "-s", tree, "-p", final, tree],
                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Failed(f"compileall could not run: {e}") from None
    if r.returncode != 0:
        last = (r.stdout.decode("utf-8", "replace").strip().splitlines() or [f"exit {r.returncode}"])[-1]
        raise Failed(f"compileall failed: {last}; nothing installed")
    for d, dirs, files in os.walk(tree):
        os.chmod(d, 0o755)
        _own(d, root)
        if os.path.basename(d) == "__pycache__":
            for n in files:
                os.chmod(os.path.join(d, n), 0o644)
                _own(os.path.join(d, n), root)
    return f"compiled with {FABRIC_PYTHON} (checked-hash .pyc)"


def _build(repo: str, sha: str, entries, managed: str, root: bool) -> tuple[str, str]:
    """The snapshot written under a temporary name beside its final one; (that name, how it was compiled)."""
    final = os.path.join(managed, f"fabric-{sha}")
    tmp = f"{final}.tmp-{os.urandom(6).hex()}"
    _mkdir(tmp, root)
    os.chmod(tmp, 0o700)          # nothing reads a half-written snapshot
    store = Store(repo)
    try:
        made = {tmp}
        for mode, oid, path in entries:
            parts = path.split("/")
            d = tmp
            for p in parts[:-1]:
                d = os.path.join(d, p)
                if d not in made:
                    _mkdir(d, root)
                    made.add(d)
            _write_new(os.path.join(d, parts[-1]), store.read(oid, "blob"), 0o755 if mode == "100755" else 0o644,
                       root)
    except BaseException:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    store.close()
    _write_new(os.path.join(tmp, MANIFEST), manifest_text(sha, entries).encode(), 0o644, root)
    try:
        compiled = _compile(tmp, final, root)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    os.chmod(tmp, 0o755)
    return tmp, compiled


def install(sha: str, repo: str = FABRIC, prefix: str = PREFIX, etc: str = ETC, rc: str = RC,
            say=print) -> None:
    """Install the snapshot of commit `sha` and the managed file it renders, step by step, each said in a line."""
    root = os.geteuid() == 0
    os.umask(0o022)
    entries = snapshot_entries(repo, sha)
    say(f"read {len(entries)} files at {sha}, every object hashed against its id")
    managed = os.path.join(prefix, "managed")
    _ensure_dir(prefix, root)
    _ensure_dir(managed, root)
    final = os.path.join(managed, f"fabric-{sha}")
    owner = 0 if root else os.geteuid()
    if os.path.isdir(final) and not os.path.islink(final) and not snapshot_problems(final, sha, entries, owner):
        say(f"snapshot {final} already in place, its MANIFEST matching")
    else:
        built, compiled = _build(repo, sha, entries, managed, root)
        say(compiled)
        if os.path.lexists(final):
            # A snapshot under this name that does not match (altered, or cut off mid-build by an older layout):
            # moved aside, not reused, and removed once the new one stands.
            bad = f"{final}.bad-{os.urandom(6).hex()}"
            os.rename(final, bad)
            os.rename(built, final)
            shutil.rmtree(bad, ignore_errors=True)
            say(f"snapshot {final} replaced: the one there did not match its MANIFEST")
        else:
            os.rename(built, final)
            say(f"snapshot {final} written")
    # Everything that can refuse runs before `current` moves, and a failed /etc write moves it back: the managed
    # file in force names hook_entry under `current`, so a swap left behind a failure would run the new snapshot's
    # code from the old file (review of #451, F15). The kept copy, which only a reboot reads, is written last.
    with open(os.path.join(final, TEMPLATE), encoding="utf-8") as f:
        rendered = render(f.read(), prefix).encode()
    _ensure_dir(etc, root)
    link = os.path.join(managed, "current")
    before = os.readlink(link) if os.path.islink(link) else None
    _point(link, os.path.basename(final), root)
    say(f"{link} -> {os.path.basename(final)}" + (f" (was {before})" if before and before != os.path.basename(final)
                                                  else ""))
    try:
        _write_atomic(os.path.join(etc, "managed-settings.json"), rendered, 0o644, root)
    except BaseException:
        if before is not None:
            _point(link, before, root)
        else:
            os.unlink(link)
        say(f"{link} put back to {before or '(none)'}: the managed file could not be written")
        raise
    kept = os.path.join(managed, "managed-settings.json")
    _write_atomic(kept, rendered, 0o644, root)
    say(f"{os.path.join(etc, 'managed-settings.json')} written (a copy kept at {kept})")
    if os.path.isdir(os.path.dirname(rc)):
        script = ("#!/bin/sh\n# agent-fabric ADR-043: /etc does not survive this AppVM's reboot and /usr/local does;"
                  " written by tools/fabric/managed_settings.py install.\n"
                  f"install -D -m 0644 {shlex.quote(kept)} {shlex.quote(os.path.join(BOOT_ETC, 'managed-settings.json'))}\n")
        _write_atomic(rc, script.encode(), 0o755, root)
        say(f"{rc} written: the managed file is restored at boot")
    for name in sorted(os.listdir(managed)):
        path = os.path.join(managed, name)
        keep = name in (os.path.basename(final), before, "current", "managed-settings.json")
        stale = SNAP_NAME.fullmatch(name) or re.fullmatch(r"fabric-[0-9a-f]{40}\.(tmp|bad)-[0-9a-f]{12}", name)
        if not keep and stale and os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
            say(f"removed {path}")
    say(f"installed: managed settings in force from fabric-{sha}")


def restore(prefix: str = PREFIX, etc: str = ETC, say=print) -> None:
    root = os.geteuid() == 0
    kept = os.path.join(prefix, "managed", "managed-settings.json")
    st = os.lstat(kept)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != (0 if root else os.geteuid()) or st.st_mode & 0o022:
        raise Failed(f"{kept} is not a regular file only its owner writes; not restored")
    with open(kept, "rb") as f:
        data = f.read()
    os.umask(0o022)
    _ensure_dir(etc, root)
    _write_atomic(os.path.join(etc, "managed-settings.json"), data, 0o644, root)
    say(f"{os.path.join(etc, 'managed-settings.json')} restored from {kept}")


# --- check ---------------------------------------------------------------------------------------------------------

# The worst finding names the state: an altered install outranks one that is not there (nothing is in force, whatever
# else cannot be read), which outranks one that cannot be read, which outranks one merely behind the ref.
SEVERITY = ("tampered", "missing", "unreadable", "drifted")
MAX_REASONS = 20


def _owned_safely(path: str, owner: int) -> str | None:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return f"{path} is a link"
    if st.st_uid != owner:
        return f"{path} is owned by uid {st.st_uid}, not {owner}"
    if st.st_mode & 0o022:
        return f"{path} is group- or other-writable ({stat.filemode(st.st_mode)})"
    return None


def check(repo: str = FABRIC, ref: str = "origin/main", prefix: str = PREFIX, etc: str = ETC, owner: int = 0,
          fabric_python: str = FABRIC_PYTHON, jq_dirs: tuple[str, ...] = JQ_DIRS) -> dict:
    """Is ADR-043 rules 1-2's install in force on this host against `ref`? Cheap: files and git plumbing only,
    no session is started (that is `probe`)."""
    found: list[tuple[str, str]] = []
    etc_file = os.path.join(etc, "managed-settings.json")
    managed = os.path.join(prefix, "managed")
    snapshot = None
    have = None
    if not os.path.lexists(etc_file):
        found.append(("missing", f"{etc_file} is absent"))
    else:
        for p in (etc, etc_file):
            why = _owned_safely(p, owner)
            if why:
                found.append(("tampered", why))
        try:
            with open(etc_file, "rb") as f:
                have = f.read()
        except OSError as e:
            found.append(("unreadable", f"{etc_file}: {e}"))
    try:
        want = render(_git(repo, "show", f"{ref}:{TEMPLATE}").decode("utf-8"), prefix).encode()
    except (Failed, ValueError, UnicodeDecodeError) as e:
        want = None
        found.append(("unreadable", f"the template at {ref}: {e}"))
    if have is not None and want is not None and have != want:
        found.append(("drifted", f"{etc_file} is not the template at {ref} rendered for {prefix}"))
    kept = os.path.join(managed, "managed-settings.json")
    if have is not None and os.path.isfile(kept):
        try:
            with open(kept, "rb") as f:
                if f.read() != have:
                    found.append(("drifted", f"{kept} is not {etc_file}: a reboot's restore would bring back another file"))
        except OSError as e:
            found.append(("unreadable", f"{kept}: {e}"))
    link = os.path.join(managed, "current")
    if not os.path.lexists(link):
        found.append(("missing", f"{link} is absent"))
    elif not os.path.islink(link):
        found.append(("tampered", f"{link} is not a link"))
    else:
        target = os.readlink(link)
        m = SNAP_NAME.fullmatch(target)
        snap = os.path.join(managed, target)
        if not m:
            found.append(("tampered", f"{link} points at {target}, not a fabric-<sha> beside it"))
        elif not os.path.isdir(snap) or os.path.islink(snap):
            found.append(("missing", f"{link} points at {target}, which is not a snapshot directory"))
        else:
            snapshot = m.group(1)
            for p in (prefix, managed, link):
                why = _owned_safely(p, owner) if p != link else (
                    None if os.lstat(p).st_uid == owner else f"{p} is owned by uid {os.lstat(p).st_uid}, not {owner}")
                if why:
                    found.append(("tampered", why))
            for why in snapshot_problems(snap, snapshot, None, owner):
                found.append(("unreadable" if "MANIFEST unreadable" in why else "tampered", why))
            try:
                with open(os.path.join(snap, MANIFEST), encoding="utf-8") as f:
                    _sha, mine = parse_manifest(f.read())
                listed = _git(repo, "ls-tree", "-r", "-z", "--full-tree", ref, "--", *SNAPSHOT)
                theirs = []
                for rec in listed.split(b"\0"):
                    if rec:
                        meta, path = rec.split(b"\t", 1)
                        mode, _kind, oid = meta.decode("ascii").split(" ")
                        theirs.append((mode, oid, path.decode("utf-8", "surrogateescape")))
                a, b = set(mine), set(theirs)
                if a != b:
                    paths = sorted({p for _m, _o, p in a ^ b})
                    found.append(("drifted", f"the snapshot fabric-{snapshot} differs from {ref} in "
                                             f"{len(paths)} path(s): {', '.join(paths[:5])}"
                                             + (" …" if len(paths) > 5 else "")))
            except (OSError, ValueError):
                pass   # an unreadable MANIFEST is reported by snapshot_problems above
            except Failed as e:
                found.append(("unreadable", f"the snapshot paths at {ref}: {e}"))
    if not os.access(fabric_python, os.X_OK):
        found.append(("missing", f"{fabric_python} is absent: every guard runs on it"))
    if not any(os.access(os.path.join(d, "jq"), os.X_OK) for d in jq_dirs):
        found.append(("missing", f"no jq in {' or '.join(jq_dirs)}: the guards ask without it"))
    state = next((s for s in SEVERITY if any(k == s for k, _w in found)), "in force")
    # A snapshot altered wholesale names every file; the first lines say what it is, the count the rest.
    reasons = [w for _k, w in found]
    if len(reasons) > MAX_REASONS:
        reasons = reasons[:MAX_REASONS] + [f"… and {len(reasons) - MAX_REASONS} more"]
    return {"state": state, "reasons": reasons, "snapshot": snapshot, "etc": etc_file, "ref": ref,
            "prefix": prefix}


# --- probe ---------------------------------------------------------------------------------------------------------

PROBE_PAYLOAD = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": "/",
                 "tool_input": {"subagent_type": "code-medium", "description": "managed-settings probe",
                                "prompt": "nothing"}}


def probe(prefix: str = PREFIX, claude: str = "claude") -> list[tuple[bool, str]]:
    """Rule 6's live test on this host: a managed guard answers (a class dispatch with no model is denied through
    the installed hook_entry.py), and a session refuses --plugin-dir (disableSideloadFlags)."""
    out = []
    entry = entry_path(prefix)
    try:
        r = subprocess.run([FABRIC_PYTHON, "-I", "-S", entry, "agent-dispatch-guard"], input=json.dumps(PROBE_PAYLOAD).encode(),
                           capture_output=True, timeout=60)
        said = r.stdout.decode("utf-8", "replace")
        out.append(('"permissionDecision":"deny"' in said.replace(" ", ""),
                    f"hook_entry.py agent-dispatch-guard on a class dispatch with no model: {said.strip()[:200] or 'nothing'}"))
    except (OSError, subprocess.TimeoutExpired) as e:
        out.append((False, f"hook_entry.py could not run: {e}"))
    try:
        r = subprocess.run([claude, "--plugin-dir", "/nonexistent", "-p", "x"], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=120)
        text = (r.stdout + r.stderr).decode("utf-8", "replace")
        out.append((r.returncode == 1 and "disableSideloadFlags" in text,
                    f"claude --plugin-dir: exit {r.returncode}, {text.strip().splitlines()[-1][:200] if text.strip() else 'nothing'}"))
    except (OSError, subprocess.TimeoutExpired) as e:
        out.append((False, f"claude could not run: {e}"))
    return out


# --- the command -----------------------------------------------------------------------------------------------------

USAGE = """usage: fabric-managed render [--prefix P]
       fabric-managed install --sha <40-hex> [--repo <path>]   (root)
       fabric-managed check [--repo <path>] [--ref origin/main] [--json]
       fabric-managed probe
       fabric-managed restore                                   (root)
The sha is main's as the remote has it, read by the operator: git ls-remote origin refs/heads/main
(then: sudo fabric-managed install --sha <that sha>)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"fabric-managed: {message}\n{USAGE}", file=sys.stderr)
        sys.exit(2)


def _may_write() -> bool:
    return os.geteuid() == 0 or any(os.environ.get(k) for k in OVERRIDES)


def main(argv: list[str]) -> int:
    ap = _Parser(prog="fabric-managed", usage=USAGE, add_help=False)
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    r = sub.add_parser("render", add_help=False)
    r.add_argument("--prefix", default=PREFIX)
    i = sub.add_parser("install", add_help=False)
    i.add_argument("--sha", required=True)
    i.add_argument("--repo", default=FABRIC)
    c = sub.add_parser("check", add_help=False)
    c.add_argument("--repo", default=FABRIC)
    c.add_argument("--ref", default="origin/main")
    c.add_argument("--json", action="store_true")
    sub.add_parser("probe", add_help=False)
    sub.add_parser("restore", add_help=False)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "render":
            with open(os.path.join(FABRIC, TEMPLATE), encoding="utf-8") as f:
                sys.stdout.write(render(f.read(), args.prefix))
            return 0
        if args.cmd == "install":
            if not SHA.fullmatch(args.sha):
                print(f"fabric-managed: --sha {args.sha!r} is not a 40-hex commit id\n{USAGE}", file=sys.stderr)
                return 2
            if not _may_write():
                raise Failed(f"install writes {PREFIX}, {ETC} and {RC}: run it as root "
                             f"(sudo fabric-managed install --sha {args.sha})")
            install(args.sha, os.path.abspath(args.repo))
            return 0
        if args.cmd == "restore":
            if not _may_write():
                raise Failed(f"restore writes {ETC}: run it as root (sudo fabric-managed restore)")
            restore()
            return 0
        if args.cmd == "check":
            res = check(os.path.abspath(args.repo), args.ref)
            if args.json:
                print(json.dumps(res, sort_keys=True))
            else:
                print(f"managed settings: {res['state']}" + (f" (fabric-{res['snapshot']})" if res["snapshot"] else ""))
                for why in res["reasons"]:
                    print(f"  {why}")
            return 0 if res["state"] == "in force" else 1
        if args.cmd == "probe":
            if os.geteuid() == 0:
                raise Failed("probe runs as the login whose sessions it tests, not as root")
            results = probe()
            for good, line in results:
                print(f"  {'ok  ' if good else 'FAIL'} {line}")
            return 0 if all(g for g, _l in results) else 1
    except Failed as e:
        print(f"fabric-managed: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"fabric-managed: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
