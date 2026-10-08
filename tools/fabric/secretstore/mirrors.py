"""tools/fabric/secretstore/mirrors.py — first contact and the parent's mirrors: bundles, seed-child, take-bundle, lineage, put, certify, rename, verify.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import base64
import contextlib
import fcntl
import json
import os
import shutil
import tempfile
from typing import TypedDict

from . import lineage as _lineage
import roots  # noqa: E402
from .core import (
    LOGIN_RE,
    StoreError,
    NotInLineage,
    login,
    AGENT_ID_RE,
    born_of,
    own_agent_id,
    store_dir,
    children_dir,
    keys_dir,
    _run,
    gpg,
    git,
)
from .keys import (
    key_of_store,
    export_key,
    _key_file_fingerprint,
    _key_agent_ids,
)
from .trust import (
    _commit,
    REFUSAL_FILE,
    trusted_base,
    _full,
    _set_base,
    _kept_refusal,
    _clear_refusal,
    _verify_incoming,
    FIRST_CONTACT_KEY,
    on_main,
    _take_verified,
)
from .lock import write_lock
from .entries import (
    _require_clean,
    _check_name,
    _one_line_off,
    _write_entry,
    _remote,
    _branch,
    _before_write,
    _after_commit,
    names,
)


# ── first contact: an account with no GitHub credential yet ───────────
# A new account's SSH key reaches it from its own store, so neither its
# first push nor its first pull can go over SSH: python-dev-01, the first
# account made after the stores replaced Doppler, stopped at its push.
# The store holds only ciphertext, its key's fingerprint and its agent id,
# so its history may travel by any channel. It travels as a git bundle,
# armored, through the host executor's stdin and stdout: the child's first
# commit to its parent, who pushes it; the parent's mirror back to the
# child once filled. Never a value, and nothing needs the two on one host.
BUNDLE_BEGIN = "-----BEGIN AGENT-FABRIC STORE BUNDLE-----"
BUNDLE_END = "-----END AGENT-FABRIC STORE BUNDLE-----"
# Named in full wherever a bundle is read: an abbreviated `main` resolves a
# tag before a branch, so a bundle holding both had its id checked on one
# commit and the other cloned and pushed (review of #76, reproduced).
MAIN = "refs/heads/main"


class LineageEntry(TypedDict):
    """One agent in identities/keys/lineage.json, keyed by its agent id:
    the login it is now, when it was born (from the id), its key's
    fingerprint, and the agent id of the parent that certified it (None
    for the root). tests/test_types.py holds the committed file to it."""
    login: str
    born: str
    fingerprint: str
    parent: str | None


def lineage_entry(aid: str, name: str, fpr: str, parent: str | None) -> LineageEntry:
    """The entry certify() records for agent `aid`, built here alone so
    tests/test_types.py holds what is written, not only what is on disk."""
    return {"login": name, "born": born_of(aid), "fingerprint": fpr, "parent": parent}


def _bundle_armored(repo: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "store.bundle")
        git(repo, "bundle", "create", path, MAIN)
        with open(path, "rb") as fh:
            body = base64.encodebytes(fh.read()).decode()
    return f"{BUNDLE_BEGIN}\n{body}{BUNDLE_END}\n"


def _bundle_file(text: str, tmp: str) -> str:
    lines = [l.strip() for l in text.strip().splitlines()]
    if len(lines) < 3 or lines[0] != BUNDLE_BEGIN or lines[-1] != BUNDLE_END:
        raise StoreError("not a store bundle (no armour); nothing taken")
    try:
        data = base64.b64decode("".join(lines[1:-1]), validate=True)
    except ValueError as e:
        raise StoreError(f"not a store bundle ({e}); nothing taken") from None
    path = os.path.join(tmp, "store.bundle")
    with open(path, "wb") as fh:
        fh.write(data)
    listed = _run(["git", "bundle", "list-heads", path], check=False)
    refs = [l.split()[-1] for l in listed.stdout.decode(errors="replace").splitlines() if l.strip()]
    if listed.returncode != 0 or refs != [MAIN]:
        raise StoreError(f"not a store bundle (it must hold {MAIN} and nothing else); nothing taken")
    return path


def _bundle_identity(path: str, tmp: str) -> tuple[str, str]:
    """(agent id, key fingerprint) the bundle's main names, read without
    touching any store."""
    peek = os.path.join(tmp, "peek")
    _run(["git", "init", "-q", peek])
    git(peek, "fetch", "-q", path, f"{MAIN}:refs/peek/main")
    def show(name: str) -> str:
        r = git(peek, "show", f"refs/peek/main:{name}", check=False)
        return (r.stdout.decode().split() or [""])[0] if r.returncode == 0 else ""
    return show(".agent-id"), show(".gpg-id")


def bundle_own() -> str:
    """This agent's store, armored, for its parent (store-enroll.sh)."""
    store = store_dir()
    key_of_store(store)
    return _bundle_armored(store)


def _rebuild_mirror(mirror: str, remote: str, agent_id: str) -> None:
    """A child's mirror made from its remote alone, every commit verified
    against the writers on the fabric's main, its base the verified head.
    A remote with nothing on main gives nothing to rebuild from. Removed
    again if anything fails, so no unverified mirror is left behind."""
    os.makedirs(children_dir(), exist_ok=True)
    git(children_dir(), "init", "-q", "-b", "main", mirror)
    try:
        git(mirror, "remote", "add", "origin", remote)
        git(mirror, "fetch", "-q", "origin", "+main:refs/remotes/origin/main", check=False)
        if git(mirror, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False).returncode != 0:
            raise StoreError(f"agent {agent_id} is on the fabric's main and its remote has no main to rebuild the "
                             "mirror from: a bundle is not first contact any more — nothing taken or pushed")
        tip = _verify_incoming(mirror, "refs/remotes/origin/main", agent_id, from_root=True)
        git(mirror, "checkout", "-q", "-B", "main", tip)
        _set_base(mirror, tip)
    except BaseException as e:
        record = os.path.join(mirror, ".git", REFUSAL_FILE)
        refused = isinstance(e, StoreError) and os.path.lexists(record)
        lost = ""
        if refused:
            # The record outlives the mirror, or status never said the
            # refusal: it read the record inside the mirror removed here
            # (review of #96).
            try:
                os.replace(record, _kept_refusal(mirror))
            except OSError as kept:
                lost = f" (its refusal record could not be kept: {type(kept).__name__})"
        shutil.rmtree(mirror, ignore_errors=True)
        if refused:
            # Removing the mirror again rebuilds the same refusal: a child
            # enrolled before ADR-042 holds unsigned history on its remote,
            # and no command rebuilds its mirror (review of #94).
            raise StoreError(f"{e}; no mirror is kept{lost} — a remote whose history its writers did not all sign "
                             "(a child enrolled before ADR-042) is the owner's to repair by hand: a clone the "
                             f"owner has checked at {mirror}, then fabric-secrets store trust-base --store {mirror}") from e
        raise


@contextlib.contextmanager
def _mirror_lock(agent_id: str):
    """One seed-child at a time per mirror on this account: two overlapping
    runs removed each other's mirror, a failed rebuild deleting the one the
    other was making (review of #94). flock(2) on <children>/<id>.lock,
    beside the mirror so a removal leaves it; the kernel drops it when the
    holder exits, however it exits, so there is no stale holder to find. A
    second run is refused at once, not queued: an enrolment re-run while
    one is going is the operator's to sequence."""
    os.makedirs(children_dir(), exist_ok=True)
    fd = os.open(os.path.join(children_dir(), f"{agent_id}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StoreError(f"another seed-child of agent {agent_id} is running on this account; "
                             "nothing taken or pushed — run it again once that one ends") from None
        yield
    finally:
        os.close(fd)


def seed_child(agent_id: str, remote: str, text: str) -> dict:
    """The parent takes a new child's first commit, as its mirror, and
    pushes it to the child's repository with the parent's own access. The
    bundle must name the agent the parent minted."""
    if not AGENT_ID_RE.match(agent_id):
        raise StoreError(f"{agent_id!r} is not an agent id")
    mirror = os.path.join(children_dir(), agent_id)
    with _mirror_lock(agent_id), tempfile.TemporaryDirectory() as tmp:
        path = _bundle_file(text, tmp)
        aid, _ = _bundle_identity(path, tmp)
        if aid != agent_id:
            raise StoreError(f"the bundle is agent {aid or '(none)'}, not {agent_id}; nothing pushed")
        # A bundle is first contact only while the child's keys are not on
        # the fabric's main. After that its writers can be read: a mirror
        # deleted and re-seeded by a re-run enrolment took a forged bundle's
        # head as trusted and pushed it with the parent's access (review of
        # ADR-042, F1). Such a mirror is rebuilt from the child's remote,
        # every commit verified from the root, and the bundle is taken on it
        # only as a verified fast-forward. A mirror that is there with no
        # base holds what nothing verified: refused, before it is touched.
        has_mirror = os.path.isdir(os.path.join(mirror, ".git"))
        if not (has_mirror and trusted_base(mirror)) and on_main(agent_id):
            if has_mirror:
                # Not "remove it to rebuild": for a child enrolled before
                # ADR-042 the rebuild refuses, and the advice looped (review
                # of #94).
                raise StoreError(f"agent {agent_id} is on the fabric's main, and its mirror {mirror} has no trusted "
                                 "base: nothing taken or pushed — its base is the owner's to record, at a head the "
                                 f"owner has checked: fabric-secrets store trust-base --store {mirror}. Removing the "
                                 "mirror rebuilds it only from a remote whose every commit its writers signed")
            _rebuild_mirror(mirror, remote, agent_id)
        if not os.path.isdir(os.path.join(mirror, ".git")):
            os.makedirs(children_dir(), exist_ok=True)
            # `clone -b main` would resolve the name again, on its own rules;
            # the checkout names the one ref the id was read from.
            _run(["git", "clone", "-q", "--no-checkout", path, mirror], label="git clone")
            git(mirror, "checkout", "-q", "-B", "main", "refs/remotes/origin/main")
            git(mirror, "remote", "set-url", "origin", remote)
        # The mirror is new or rebuilt under _mirror_lock; its write lock
        # is taken too, so a put that arrives meanwhile waits for the take.
        with write_lock(mirror):
            _seed_take(mirror, path, remote, agent_id)
    return {"agent_id": agent_id, "mirror": mirror, "remote": remote}


def _seed_take(mirror: str, path: str, remote: str, agent_id: str) -> None:
    git(mirror, "fetch", "-q", path, f"+{MAIN}:refs/first-contact/main")
    # First contact (ADR-042, the coordinator's ruling of 2026-10-04):
    # the child's own first commit is signed by a key not yet on the
    # fabric's main — its keys merge after enrolment — so the bundle's
    # head, handed over the host executor the parent drives, is the
    # mirror's trusted base. Only from a bundle, and only for a mirror
    # with none: a fetch never sets a base.
    if trusted_base(mirror) is None:
        _set_base(mirror, _full(mirror, "refs/first-contact/main"))
    # Whatever the remote already has, then the child's commit, each only
    # as a verified fast-forward — a fresh clone included: a mirror deleted
    # by hand after the parent's puts is cloned again from the child's
    # bundle alone, behind the remote, and its push was refused as
    # non-fast-forward (a carried review item).
    git(mirror, "fetch", "-q", "origin")
    if git(mirror, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False).returncode == 0:
        _take_verified(mirror, "refs/remotes/origin/main", agent_id)
    _take_verified(mirror, "refs/first-contact/main", agent_id)
    git(mirror, "push", "-q", "-u", "origin", "HEAD:main")


def child_bundle(who: str) -> str:
    """A child's store as its parent's mirror holds it, brought up to the
    remote first, armored: everything the parent wrote, encrypted to the
    child's key, for the child's first sync."""
    return _bundle_armored(refresh_mirror(who))


def refresh_mirror(who: str) -> str:
    """A child's mirror brought up to its remote by the verified fetch
    (ADR-042 rule 3): the only way a mirror moves, never a raw pull. Its
    path."""
    aid, _ = resolve(who)
    mirror = os.path.join(children_dir(), aid)
    if not os.path.isdir(os.path.join(mirror, ".git")):
        raise StoreError(f"no mirror of {who} here (store-enroll.sh first)")
    with write_lock(mirror):
        git(mirror, "fetch", "-q", "origin", "+main:refs/remotes/origin/main")
        _take_verified(mirror, "refs/remotes/origin/main", aid)
    return mirror


def take_bundle(text: str) -> dict:
    """The child fast-forwards its store from its parent's bundle, and
    only from one of its own store: the same agent id and the same key."""
    store = store_dir()
    with write_lock(store):
        fpr, own = key_of_store(store), own_agent_id(store)
        with tempfile.TemporaryDirectory() as tmp:
            path = _bundle_file(text, tmp)
            aid, gpg_id = _bundle_identity(path, tmp)
            if aid != own or gpg_id != fpr:
                raise StoreError(f"the bundle is agent {aid or '(none)'} with key {gpg_id or '(none)'}, "
                                 f"not this store ({own}, {fpr}); nothing taken")
            # Quarantined, verified, then taken (ADR-042 rule 3): the bundle's
            # commits reach the store's refs only once every one verifies.
            git(store, "fetch", "-q", path, f"+{MAIN}:refs/agent-fabric/incoming")
            try:
                if not on_main(own):
                    # First contact (the coordinator's ruling of 2026-10-04): a new
                    # agent takes its parent's first bundle before its keys reach
                    # main, so its writers cannot be read yet. That bundle — only a
                    # bundle, carried by the host executor the parent drives —
                    # becomes the store's base, once; a second one before the
                    # merge refuses, and a fetch never does this.
                    if git(store, "config", "--get", FIRST_CONTACT_KEY, check=False).returncode == 0:
                        raise StoreError(f"agent {own} is not yet on the fabric's main, and this store has had its "
                                         "first contact: nothing more is taken until its keys are merged — fetch the fabric")
                    tip = _full(store, "refs/agent-fabric/incoming")
                    git(store, "merge", "-q", "--ff-only", tip)
                    _set_base(store, tip)
                    git(store, "config", FIRST_CONTACT_KEY, tip)
                    _clear_refusal(store)
                else:
                    tip = _take_verified(store, "refs/agent-fabric/incoming")
                git(store, "update-ref", "refs/remotes/origin/main", tip)
            finally:
                git(store, "update-ref", "-d", "refs/agent-fabric/incoming", check=False)
        head = git(store, "rev-parse", "--short", "HEAD").stdout.decode().strip()
        return {"agent_id": aid, "head": head, "names": len(names(store))}


# ── the parent ────────────────────────────────────────────────────────
def lineage(fabric: str | None = None) -> dict[str, LineageEntry]:
    return _lineage.lineage(fabric or roots.operator_root())


def _write_lineage(doc: dict, fabric: str | None = None) -> None:
    path = os.path.join(keys_dir(fabric), "lineage.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    os.replace(path + ".tmp", path)


def resolve(who: str, doc: dict | None = None, fabric: str | None = None) -> tuple[str, dict]:
    """An agent named by its id or by its current login -> (id, record)."""
    doc = lineage(fabric) if doc is None else doc
    if AGENT_ID_RE.match(who):
        if who not in doc:
            raise NotInLineage(f"agent {who} is not in identities/keys/lineage.json")
        return who, doc[who]
    if not LOGIN_RE.match(who):
        raise StoreError(f"{who!r} is neither a login nor an agent id")
    hits = [(a, r) for a, r in doc.items() if isinstance(r, dict) and r.get("login") == who]
    if not hits:
        raise NotInLineage(f"{who}: no agent with that login in identities/keys/lineage.json")
    if len(hits) > 1:
        raise StoreError(f"{who}: {len(hits)} agents with that login in identities/keys/lineage.json")
    return hits[0]


def put(child: str, name: str, value: bytes, store: str | None = None, fabric: str | None = None,
        *, exact: bool = False) -> dict:
    """The parent writes an entry into a child's store: encrypted to the
    child's COMMITTED key (never imported), which must be the key the
    store says it is encrypted to. The parent cannot read what it wrote."""
    aid, rec = resolve(child, fabric=fabric)
    key_file = os.path.join(keys_dir(fabric), f"{aid}.asc")
    if not os.path.exists(key_file):
        raise StoreError(f"no committed key for {rec.get('login')} ({key_file})")
    store = store or os.path.join(children_dir(), aid)
    _check_name(name)
    with write_lock(store):
        # Brought up to date FIRST: a mirror still naming the old key must not
        # pass the check and then receive a re-keyed .gpg-id with the pull.
        _require_clean(store)
        _before_write(store)
        committed = _key_file_fingerprint(key_file)
        if key_of_store(store) != committed:
            raise StoreError(f"{rec.get('login')}'s store is encrypted to another key than the committed one; "
                             "a store and its key must agree before anything is written")
        _write_entry(store, name, value if exact else _one_line_off(value), ["--recipient-file", key_file])
        changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
        if changed:
            try:
                # A failed commit puts the mirror back to what it held itself
                # (_commit; review of #69, and the reset's failure said, #70).
                _commit(store, f"parent {login()}: put {name}")
            except StoreError as failed:
                raise StoreError(f"{rec.get('login')}: {failed}") from failed
            try:
                _after_commit(store)
            except StoreError as pushed:
                # The mirror is the parent's view of the child's store, never a
                # record of its own: a put that did not reach the remote is
                # undone here, or the next look at the mirror reads the entry
                # as held and the next put pushes it (review of #69, F1). The
                # agent's own store keeps an unpushed commit instead, and
                # _push_if_ahead retries it — that store IS the record.
                if _remote(store):
                    r = git(store, "reset", "-q", "--hard", f"origin/{_branch(store)}", check=False)
                    if r.returncode != 0:
                        why = ([l for l in r.stderr.decode(errors="replace").splitlines() if l.strip()] or [f"exit {r.returncode}"])[-1]
                        raise StoreError(f"{rec.get('login')}: {pushed}; and the mirror could not be reset to its remote "
                                         f"({store}: {why}) — reset it before the next put") from pushed
                raise
        return {"child": rec.get("login"), "agent_id": aid, "name": name, "changed": changed}


def certify(child: str | None, key_file: str | None, fabric: str | None = None) -> dict:
    """The parent attests a child's key with its own (the birth
    certificate), and commits the certified public half and the lineage,
    keyed by the agent id the key carries. --root: the coordinator
    records its own key, with no parent."""
    me, doc = login(), lineage(fabric)
    my_fpr, my_id = key_of_store(), own_agent_id()
    if not my_id:
        raise StoreError("this store has no agent id yet: store-enroll.sh --self")
    kd = keys_dir(fabric)
    os.makedirs(kd, exist_ok=True)

    def record(aid: str, name: str, fpr: str, parent: str | None) -> None:
        for other, r in doc.items():
            if other != aid and isinstance(r, dict) and r.get("login") == name:
                raise StoreError(f"the login {name} is already agent {other}; a login reused is a new agent "
                                 "only after the old one is retired")
        if aid in doc and doc[aid].get("login") != name:
            raise StoreError(f"agent {aid} is {doc[aid].get('login')}, not {name}: a rename is `store rename`")
        doc[aid] = lineage_entry(aid, name, fpr, parent)
        _write_lineage(doc, fabric)

    if child is None:
        record(my_id, me, my_fpr, None)
        with open(os.path.join(kd, f"{my_id}.asc"), "w", encoding="utf-8") as fh:
            fh.write(export_key(my_fpr))
        return {"login": me, "agent_id": my_id, "fingerprint": my_fpr, "parent": None}
    if not LOGIN_RE.match(child) or child == me:
        raise StoreError(f"{child!r} is not another login")
    fpr = _key_file_fingerprint(key_file)
    ids = _key_agent_ids(key_file)
    if len(ids) != 1:
        raise StoreError(f"the child's key carries {len(ids)} agent ids, not one: it was not made by `store init --agent-id`")
    aid = ids[0]
    # The key's name part is not checked against the login: what makes the
    # key the agent's is this certification and the id it carries (ADR-038
    # §5 rule 2, ADR-039), and a test cannot make a second Unix user to
    # name one.
    gpg("--import", key_file)
    gpg("--default-key", my_fpr, "--quick-sign-key", fpr)
    record(aid, child, fpr, my_id)
    with open(os.path.join(kd, f"{aid}.asc"), "w", encoding="utf-8") as fh:
        fh.write(export_key(fpr))
    return {"login": child, "agent_id": aid, "fingerprint": fpr, "parent": my_id}


def rename(old: str, new: str, fabric: str | None = None) -> dict:
    """A login renamed: its one lineage field. The id, the key, the store
    and its repository keep their names (ADR-039)."""
    doc = lineage(fabric)
    aid, rec = resolve(old, doc)
    if not LOGIN_RE.match(new):
        raise StoreError(f"{new!r} is not a login")
    if any(isinstance(r, dict) and r.get("login") == new for r in doc.values()):
        raise StoreError(f"the login {new} is already an agent's")
    rec["login"] = new
    _write_lineage(doc, fabric)
    return {"agent_id": aid, "from": old if not AGENT_ID_RE.match(old) else None, "login": new}


def verify(fabric: str | None = None) -> list[str]:
    """Every committed key against lineage.json: lineage.py's verify, the
    one the lint runs, on this fabric."""
    return _lineage.verify(fabric or roots.operator_root())
