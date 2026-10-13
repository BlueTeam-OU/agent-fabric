"""tools/fabric/secretstore/settings.py — an agent's settings, written to
its own store below settings/ (agent-fabric ADR-056 §5 rule 1: a persona
reaches the agent's repository as ONE commit).
A part of secret_store.py, which re-exports it.

Contract of `settings_put(src)`:
  input   a directory; its tree is copied to <store>/settings/, adding and
          overwriting, never deleting what the store already holds there.
  refused before the store is touched, each naming the path: a source that
          is not a directory or is a link; an entry that is not a plain
          file or directory when opened (a link, device, FIFO, socket); an
          entry that cannot be read, a file over its size cap, the tree
          over its total cap, nested deeper than MAX_DEPTH, a file with
          several hard links; a name git treats as its own (.git*:
          .gitignore would silently drop files from the commit).
  refused under the lock, after the store is brought up to its remote and
          before anything is written: when the tree carries a profile or an
          avatar, the profile that will stand (the tree's, else the store's)
          is not JSON, does not match identities/schemas/persona-profile.
          schema.json (read from the operator's checkout; a checkout without
          it refuses rather than skipping the check), names another agent
          than this store's, or does not agree with the avatar that will
          stand (the tree's, else the store's): avatar.sha256 is the sha256
          of avatar.png; a path below settings/ that already holds a link in
          the store (settings/ itself included), or untracked or ignored files
          left there, or a file flagged assume-unchanged or skip-worktree; a
          store with no remote (the commit would reach no one).
  signals Ctrl-C, SIGTERM and SIGHUP before the commit exists undo the write
          and end as a one-line refusal; SIGKILL cannot be handled and leaves
          the store dirty, which the next run refuses by name.
  effect  under the store's write lock, brought up to its remote first
          (verified, ADR-042), then ONE commit signed through the store's
          own path ("agent <login>: settings"), then pushed. Nothing
          changed is no commit, and an earlier failed push is caught up.
          A failure after the first file is written puts the store back
          as it was: tracked files reset, files this run created removed.
  result  {"files": [settings/-relative paths], "changed": bool}.

Every component of the source path is opened without following a link (the
ancestors by O_PATH, so a directory that only grants search is passed
through): whoever controls one of them could otherwise point the walk at the
agent's own directories. A path with a link in it is resolved by its caller
(realpath) and the real directory named.

Why descriptors: the source may be writable by another account (the threat
model), so a check by path followed by an open by path is a race: the
entry can become a link between the two, and the agent's own private file
would be committed and pushed. Every entry is opened O_NOFOLLOW from its
parent's descriptor, judged by fstat on what was opened, and read within
its cap.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import signal
import secrets
import stat

from . import entries
from .core import StoreError, git, login, own_agent_id, store_dir, roots
from .lock import write_lock
from .trust import _commit

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TREE_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 16
MAX_FILES = 1000
PROFILE = "profile.json"
AVATAR = "avatar.png"
SCHEMA_REL = os.path.join("identities", "schemas", "persona-profile.schema.json")
_OPEN = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def _read_tree(src: str) -> dict[str, bytes]:
    """The source's regular files by their path below it; anything else, or
    anything unreadable, refuses by path."""
    files: dict[str, bytes] = {}
    total = 0

    def walk(dfd: int, prefix: str, depth: int) -> None:
        nonlocal total
        if depth > MAX_DEPTH:
            raise StoreError(f"{prefix}: nested deeper than {MAX_DEPTH} levels; nothing written")
        try:
            names = sorted(os.listdir(dfd))
        except OSError as e:
            raise StoreError(f"{prefix or src}: {e.strerror or e}; nothing written") from None
        for name in names:
            rel = os.path.join(prefix, name)
            if name.startswith(".git"):
                raise StoreError(f"{rel}: a name git reads as its own (.git*) is refused; nothing written")
            try:
                before = os.stat(name, dir_fd=dfd, follow_symlinks=False)
            except OSError as e:
                raise StoreError(f"{rel}: {e.strerror or e}; nothing written") from None
            if stat.S_ISDIR(before.st_mode):
                if depth == 0 and name in (PROFILE, AVATAR):
                    raise StoreError(f"{name}: must be a plain file, not a directory; nothing written")
                try:
                    child = os.open(name, _OPEN | os.O_DIRECTORY, dir_fd=dfd)
                except OSError as e:
                    raise StoreError(f"{rel}: {e.strerror or e}; nothing written") from None
                try:
                    walk(child, rel, depth + 1)
                finally:
                    os.close(child)
                continue
            try:
                # O_NONBLOCK: a FIFO swapped in after the stat must not hang the open.
                fd = os.open(name, _OPEN | os.O_NONBLOCK, dir_fd=dfd)
            except OSError as e:
                why = "a link is not followed" if e.errno == errno.ELOOP else (e.strerror or str(e))
                raise StoreError(f"{rel}: {why}; nothing written") from None
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode):
                    raise StoreError(f"{rel}: not a plain file or directory (a link, device, FIFO or socket is "
                                     "refused); nothing written")
                if opened.st_nlink != 1:
                    # Another account's hardlink to a file of the agent's own looks like a plain file.
                    raise StoreError(f"{rel}: a file with several hard links is refused; nothing written")
                with os.fdopen(fd, "rb", closefd=False) as fh:
                    data = fh.read(MAX_FILE_BYTES + 1)
            except OSError as e:
                raise StoreError(f"{rel}: {e.strerror or e}; nothing written") from None
            finally:
                os.close(fd)
            total += len(data)
            if len(data) > MAX_FILE_BYTES or total > MAX_TREE_BYTES:
                raise StoreError(f"{rel}: the tree is over the size cap ({MAX_FILE_BYTES} a file, "
                                 f"{MAX_TREE_BYTES} in all); nothing written")
            files[rel] = data
            if len(files) > MAX_FILES:
                raise StoreError(f"more than {MAX_FILES} files; nothing written")

    # Every component of the path is opened O_NOFOLLOW from its parent, the source's own included: a link anywhere
    # on it (another account owning one of the directories) would point the walk at the agent's own files.
    # Whoever needs a link in the path resolves it first (realpath) and names the directory itself.
    parts = [part for part in os.path.abspath(src).split(os.sep) if part]
    # O_PATH for the ancestors: it needs no read permission, so a directory that only grants search (0711, the usual way
    # to share inside another account's home) is passed through; only the source itself is opened for listing.
    top = os.open(os.sep, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        here = os.sep
        for i, part in enumerate(parts):
            here = os.path.join(here, part)
            last = i == len(parts) - 1
            try:
                nxt = os.open(part, (_OPEN if last else os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC) | os.O_DIRECTORY, dir_fd=top)
            except OSError as e:
                # O_NOFOLLOW|O_DIRECTORY on a link answers ENOTDIR or ELOOP, by kernel: ask what it is.
                try:
                    is_link = stat.S_ISLNK(os.stat(part, dir_fd=top, follow_symlinks=False).st_mode)
                except OSError:
                    is_link = False
                why = ("a link is not followed, in any component of the path" if is_link or e.errno == errno.ELOOP
                       else "not a directory" if e.errno == errno.ENOTDIR else (e.strerror or str(e)))
                raise StoreError(f"{here}: {why}; nothing written") from None
            os.close(top)
            top = nxt
        if not parts:
            os.close(top)
            top = os.open(os.sep, _OPEN | os.O_DIRECTORY)
        walk(top, "", 0)
    finally:
        os.close(top)
    if not files:
        raise StoreError(f"{src}: no files in it; nothing written")
    return files


def _load_profile(raw: bytes, agent_id: str) -> dict:
    from lint_rules.schema import validate_json
    schema_path = os.path.join(roots.operator_root(), SCHEMA_REL)
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as e:
        raise StoreError(f"{PROFILE} cannot be checked: {schema_path}: {e}; nothing written") from None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise StoreError(f"{PROFILE} is not JSON ({e}); nothing written") from None
    problems = validate_json(schema, doc, PROFILE)
    if problems:
        raise StoreError("; ".join(problems[:5]) + "; nothing written")
    if doc["agent_id"] != agent_id:
        raise StoreError(f"{PROFILE} is for agent {doc['agent_id']}, this store is agent {agent_id}; nothing written")
    return doc


def _held(store: str, name: str) -> bytes | None:
    path = _destination(store, name)
    if not os.path.lexists(path):
        return None
    if not os.path.isfile(path):
        raise StoreError(f"settings/{name} in the store is not a plain file; nothing written")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as e:
        raise StoreError(f"settings/{name} in the store: {e.strerror or e}; nothing written") from None


def _check_standing(files: dict[str, bytes], store: str, agent_id: str) -> None:
    """The profile and the avatar that will stand after the write agree.
    Read under the lock, after the store caught up: the remote may hold
    another avatar than the one this run last saw."""
    if PROFILE not in files and AVATAR not in files:
        return
    raw = files.get(PROFILE, _held(store, PROFILE))
    if raw is None:
        return   # an avatar with no profile anywhere: nothing yet names its hash
    doc = _load_profile(raw, agent_id)
    avatar = files.get(AVATAR, _held(store, AVATAR))
    if avatar is None:
        raise StoreError(f"{PROFILE} names {AVATAR}, which neither the tree nor the store holds; nothing written")
    if hashlib.sha256(avatar).hexdigest() != doc["avatar"]["sha256"]:
        raise StoreError(f"{PROFILE}: avatar.sha256 is not the sha256 of {AVATAR}; nothing written")


def _destination(store: str, rel: str) -> str:
    """Below <store>/settings/ with no link on the way: a link committed
    there would carry the write out of settings/."""
    here = store
    for part in ("settings", *rel.split(os.sep)):
        here = os.path.join(here, part)
        if os.path.islink(here):
            raise StoreError(f"settings/{rel}: {os.path.relpath(here, store)} is a link in the store; nothing written")
    return here


def _put_file(dest: str, data: bytes) -> None:
    """Replaced whole or not at all: a crash leaves the old file."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = os.path.join(os.path.dirname(dest), f".settings-{secrets.token_hex(8)}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o644)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _missing_dirs(store: str, dests: list[str]) -> list[str]:
    """The directories below settings/ these writes will make, deepest first."""
    root = os.path.join(store, "settings")
    wanted: set[str] = set() if os.path.lexists(root) else {root}
    for dest in dests:
        here = os.path.dirname(dest)
        while here != root and not os.path.lexists(here):
            wanted.add(here)
            here = os.path.dirname(here)
    return sorted(wanted, key=len, reverse=True)


@contextlib.contextmanager
def _masked():
    """A second signal must not cut the undo, or the decision to undo, short."""
    old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGHUP, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old)


def _undo(store: str, created: list[str], made_dirs: list[str] = ()) -> None:
    """The store as it was: tracked files back, the files and directories this run made gone."""
    with _masked():
        _undo_unmasked(store, created, made_dirs)


def _undo_unmasked(store: str, created: list[str], made_dirs: list[str]) -> None:
    r = git(store, "reset", "-q", "--hard", "HEAD", check=False)
    lock = os.path.join(store, ".git", "index.lock")
    if r.returncode != 0 and os.path.exists(lock):
        # A signal killed the git commit that held it (subprocess.run kills its child on an interrupt): git cannot
        # clean up after SIGKILL. This run holds the store's write lock and its own git is dead, so the lock is stale.
        os.unlink(lock)
        r = git(store, "reset", "-q", "--hard", "HEAD", check=False)
    if r.returncode != 0:
        why = ([l for l in r.stderr.decode(errors="replace").splitlines() if l.strip()] or [f"exit {r.returncode}"])[-1]
        raise StoreError(f"the write failed, and {store} could not be reset ({why}) — reset it before the next write")
    for path in created:
        try:
            os.unlink(path)
        except OSError:
            pass   # never made (the write failed before it), or its directory is a file: nothing to remove
    for path in made_dirs:
        try:
            os.rmdir(path)
        except OSError:
            pass   # never made, or not empty


def _terminate(signum, _frame):
    raise KeyboardInterrupt(f"signal {signum}")


def settings_put(src: str) -> dict:
    # SIGTERM and SIGHUP end a Python process without an exception: raised here, the undo below runs for them
    # as for Ctrl-C. SIGKILL cannot be handled: it leaves the store dirty, and the next run refuses it by name.
    # A caller that ignores SIGHUP (nohup) keeps ignoring it.
    state = {"committed": False}
    previous = {s: signal.signal(s, _terminate) for s in (signal.SIGTERM, signal.SIGHUP)
                if signal.getsignal(s) != signal.SIG_IGN}
    try:
        return _put(_read_tree(src), state)
    except KeyboardInterrupt as e:
        what = str(e) or "Ctrl-C"
        if state["committed"]:
            raise StoreError(f"interrupted ({what}) after the commit was made: it is in the store, and the next "
                             "settings-put pushes it") from None
        raise StoreError(f"interrupted ({what}), the write undone; nothing written") from None
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def _put(files: dict[str, bytes], state: dict) -> dict:
    store = store_dir()
    aid = own_agent_id(store) if os.path.isdir(store) else None
    if not aid:
        raise StoreError("this account has no store yet (fabric-secrets store init); nothing written")
    with write_lock(store):
        entries._require_clean(store)
        if not entries._remote(store):
            # _before_write and _after_commit skip a store with no remote: the write would "succeed" and reach no one.
            raise StoreError("this store has no remote to push its commit to; nothing written")
        entries._before_write(store)
        left = git(store, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", "settings").stdout.decode().strip()
        if left:
            raise StoreError(f"{store} has untracked or ignored files below settings/ ({left.splitlines()[0][3:]}); nothing written")
        flagged = [l for l in git(store, "ls-files", "-v", "--", "settings").stdout.decode("utf-8", "surrogateescape").splitlines()
                   if l[:1].islower() or l[:1] == "S"]
        if flagged:
            # assume-unchanged / skip-worktree: git add would skip the file while the profile naming its hash is staged.
            raise StoreError(f"{flagged[0][2:]} carries an assume-unchanged or skip-worktree flag in the store; nothing written")
        _check_standing(files, store, aid)
        dests = {rel: _destination(store, rel) for rel in files}
        created = [d for d in dests.values() if not os.path.lexists(d)]
        made_dirs = _missing_dirs(store, list(dests.values()))
        head = git(store, "rev-parse", "HEAD").stdout
        try:
            for rel, data in sorted(files.items()):
                _put_file(dests[rel], data)
            git(store, "add", "-A", "--", "settings")
            staged_all = set(git(store, "ls-files", "-z", "--", "settings").stdout.decode("utf-8", "surrogateescape").split("\0"))
            missing = sorted(f"settings/{rel}" for rel in files if f"settings/{rel}" not in staged_all)
            if missing:
                raise StoreError(f"{missing[0]} was not staged (git ignores it); nothing written")
            changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
        except BaseException as e:
            # Any failure, an interrupt too: the next write refuses a dirty store until it is reset by hand.
            _undo(store, created, made_dirs)
            if isinstance(e, OSError):
                raise StoreError(f"{e.filename or 'settings'}: {e.strerror or e}; nothing written") from None
            raise
        if changed:
            try:
                _commit(store, f"agent {login()}: settings")
            except BaseException:
                # _commit resets after its own failures; an interrupt (signing waits on gpg) bypasses that.
                with _masked():
                    if git(store, "rev-parse", "HEAD").stdout == head:
                        _undo(store, created, made_dirs)
                    else:
                        state["committed"] = True
                raise
            state["committed"] = True
            entries._after_commit(store)
        else:
            entries._push_if_ahead(store)
        return {"files": sorted(files), "changed": changed}
