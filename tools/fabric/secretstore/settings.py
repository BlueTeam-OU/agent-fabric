"""tools/fabric/secretstore/settings.py — an agent's settings, written to
its own store below settings/ (agent-fabric ADR-056 §5 rule 1: a persona
reaches the agent's repository as ONE commit).
A part of secret_store.py, which re-exports it.

Contract of `settings_put(src)`:
  input   a directory; its tree is copied to <store>/settings/, adding and
          overwriting, never deleting what the store already holds there.
  refused before the store is touched, each naming the path: a source that
          is not a directory or is a link; any entry in it that is not a
          plain file or directory (a link, a device, a socket); a file or
          the whole tree over its size cap; settings/profile.json that is
          not JSON, does not match identities/schemas/persona-profile.schema.json
          (read from the operator's checkout; a checkout without it
          refuses rather than skipping the check), names another agent
          than this store's, or whose avatar.sha256 is not the sha256 of
          the avatar.png the tree carries (or of the one the store holds,
          when the tree carries none).
  effect  under the store's write lock, brought up to its remote first
          (verified, ADR-042), then ONE commit signed through the store's
          own path ("agent <login>: settings"), then pushed. Nothing
          changed is no commit, and an earlier failed push is caught up.
  result  {"files": [relative paths written, settings/-relative],
           "changed": bool}.
Nothing here reads or writes env/: a name that would reach it cannot, because
every destination is joined below settings/ from a path that has been
checked to hold no "..", no absolute part and no link.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile

from . import entries
from .core import StoreError, git, login, own_agent_id, store_dir, roots
from .lock import write_lock
from .trust import _commit

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TREE_BYTES = 64 * 1024 * 1024
PROFILE = "profile.json"
AVATAR = "avatar.png"
SCHEMA_REL = os.path.join("identities", "schemas", "persona-profile.schema.json")


def _read_tree(src: str) -> dict[str, bytes]:
    """The source's regular files by their path below it; any other kind of
    entry refuses, and nothing is read through a link."""
    try:
        top = os.lstat(src)
    except OSError as e:
        raise StoreError(f"{src}: {e.strerror or e}; nothing written") from None
    if not stat.S_ISDIR(top.st_mode):
        raise StoreError(f"{src} is not a directory (a link is not followed); nothing written")
    files: dict[str, bytes] = {}
    total = 0
    for here, dirs, names in os.walk(src, followlinks=False):
        for name in [*dirs, *names]:
            path = os.path.join(here, name)
            mode = os.lstat(path).st_mode
            rel = os.path.relpath(path, src)
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise StoreError(f"{rel}: not a plain file or directory (a link, device or socket is refused); "
                                 "nothing written")
            size = os.lstat(path).st_size
            total += size
            if size > MAX_FILE_BYTES or total > MAX_TREE_BYTES:
                raise StoreError(f"{rel}: the tree is over the size cap ({MAX_FILE_BYTES} a file, "
                                 f"{MAX_TREE_BYTES} in all); nothing written")
            with open(path, "rb") as fh:
                files[rel] = fh.read()
    return files


def _validate_profile(files: dict[str, bytes], held_avatar: bytes | None, agent_id: str) -> None:
    raw = files.get(PROFILE)
    if raw is None:
        return
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
    avatar = files.get(AVATAR, held_avatar)
    if avatar is None:
        raise StoreError(f"{PROFILE} names {AVATAR}, which neither the tree nor the store holds; nothing written")
    if hashlib.sha256(avatar).hexdigest() != doc["avatar"]["sha256"]:
        raise StoreError(f"{PROFILE}: avatar.sha256 is not the sha256 of {AVATAR}; nothing written")


def _put_file(dest: str, data: bytes) -> None:
    """Replaced whole or not at all: a crash leaves the old file."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".settings-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def settings_put(src: str) -> dict:
    files = _read_tree(src)
    store = store_dir()
    aid = own_agent_id(store) if os.path.isdir(store) else None
    if not aid:
        raise StoreError("this account has no store yet (fabric-secrets store init); nothing written")
    held = os.path.join(store, "settings", AVATAR)
    held_avatar = None
    if os.path.isfile(held):
        with open(held, "rb") as fh:
            held_avatar = fh.read()
    _validate_profile(files, held_avatar, aid)
    with write_lock(store):
        entries._require_clean(store)
        entries._before_write(store)
        for rel, data in sorted(files.items()):
            _put_file(os.path.join(store, "settings", rel), data)
        git(store, "add", "-A", "--", "settings")
        changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
        if changed:
            _commit(store, f"agent {login()}: settings")
            entries._after_commit(store)
        else:
            entries._push_if_ahead(store)
        return {"files": sorted(files), "changed": changed}
