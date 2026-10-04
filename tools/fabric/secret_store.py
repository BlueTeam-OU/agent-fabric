#!/usr/bin/env python3
"""tools/fabric/secret_store.py — an agent's own encrypted secrets
(agent-fabric ADR-038), behind `fabric-secrets store …`.

    fabric-secrets store init --agent-id ID [--remote URL]
                                                 in the account: its key and its store
    fabric-secrets store mint-id BORN            a new agent id, a UUIDv7 of that birth (ADR-039)
    fabric-secrets store id                      this store's agent id (exit 3: none yet)
    fabric-secrets store id-of LOGIN             the agent id lineage.json records for a login
                                                 (exit 3: no agent with that login)
    fabric-secrets store rename OLD NEW          a login renamed; its id, key and store stay
    fabric-secrets store set NAME                the agent writes an entry (value on stdin)
    fabric-secrets store export-key              the agent's PUBLIC key, armored (for its parent)
    fabric-secrets store push                    the store to its remote
    fabric-secrets store bundle                  this store, armored, for its parent (first contact)
    fabric-secrets store take-bundle             the child takes its parent's bundle (stdin)
    fabric-secrets store seed-child ID --remote URL
                                                 the parent takes a new child's bundle (stdin) as its
                                                 mirror and pushes it
    fabric-secrets store child-bundle LOGIN|ID   the parent's mirror of a child, armored
    fabric-secrets store refresh-mirror LOGIN|ID the parent's mirror of a child, brought up to its remote
                                                 by the verified fetch (ADR-042)
    fabric-secrets store trust-base [COMMIT] [--store DIR]
                                                 the commit up to which the store's history is
                                                 trusted unsigned (ADR-042; the migration, once)
    fabric-secrets store names [--json]          the entries, by name
    fabric-secrets store put LOGIN|ID NAME [--store DIR]
                                                 the parent writes into a child's store
                                                 (value on stdin; the child's committed key)
    fabric-secrets store certify LOGIN KEYFILE | --root
                                                 the parent attests a child's key
    fabric-secrets store verify                  every committed key against its lineage
    fabric-secrets store paper [--out FILE]      the key and its revocation, for the owner
    fabric-secrets store recovery-key init       the OWNER, in a terminal: the recovery key (passphrase-protected,
                                                 its private half only in Proton)
    fabric-secrets store recovery-copy           this login's recovery copy, encrypted to the recovery key
    fabric-secrets store backup [--verify]       every store held, as git bundles, into Proton Drive
    fabric-secrets store template-set SLUG       a Claude account's setup-token into this
                                                 (the coordinator's) store (value on stdin)
    fabric-secrets store templates [--json]      the templates, by fingerprint
    fabric-secrets store assign SLUG LOGIN|ID... each agent's store gets the template's token
                                                 (ADR-031, through its parent)

The store is a git repository in the layout pass(1) reads, so QtPass and
browserpass open it: `.gpg-id` names the key, and each secret is
`env/<NAME>.gpg`, its value on the first line. It is encrypted to the
agent's key alone. Anyone holding the committed public key can add an
entry, and only the agent can read one: the parent writes and never reads.

A key is an agent's when its public half is committed at
`identities/keys/<agent id>.asc` with its parent's certification on the
user id addressed to that id, and `identities/keys/lineage.json` records
that parent (ADR-039: stored under the id, typed as the login). Placement is not
part of it: no host is named anywhere, and nothing here needs the
parent and the child on one machine. They meet only through git.

WHO MAY WRITE A STORE (ADR-042). Every commit to a store is signed by its
writer's own key, and a store takes in only commits signed by its writers:
the agent's own key and its recorded parent's, as lineage.json and
identities/keys/ stand at the fabric checkout's origin/main. pull, the
write paths' fetch, take-bundle, seed-child, child-bundle, refresh-mirror
and push's fast-forward verify every commit beyond the store's trusted
base (agent-fabric.trustedbase in its .git/config, set by `trust-base` or
a new store's init, moved forward by each verified fetch). A refusal names
the commit and why, applies nothing, and is kept beside the store for
`fabric-secrets status` and `fabric-ctl keys` until a verified fetch
succeeds. First contact, before a new agent's keys reach main, is the one
exception, on both sides and only through a bundle: seed-child records the
child's first bundle as its mirror's base, and the child's first
take-bundle records its parent's (once).

No function here prints a secret value. `values()` returns them to the
caller in-process (fabric-secrets sync); everything else deals in names,
fingerprints and paths.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# The parts are found beside this file however it is loaded: the CLI runs it
# as a script, and tests/test_first_contact.py loads it by its path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secretstore.core import (  # noqa: E402
    HERE,
    FABRIC_ROOT,
    NAME_RE,
    LOGIN_RE,
    UID_DOMAIN,
    StoreError,
    NotInLineage,
    login,
    AGENT_ID_RE,
    REPO_PREFIX,
    mint_agent_id,
    born_of,
    born_ms_of,
    own_agent_id,
    home,
    store_dir,
    children_dir,
    keys_dir,
    _GIT_REPO_ENV,
    _git_scrubbed,
    _run,
    _failure,
    GPG_COMMANDS,
    gpg,
    git,
)
from secretstore.keys import (  # noqa: E402
    fingerprints,
    key_of_store,
    KEY_USES,
    _key_caps,
    _ensure_use_subkeys,
    uid_of,
    export_key,
    _signing_args,
    _signing_subkeys,
    _key_file_fingerprint,
    _key_agent_ids,
)
from secretstore.trust import (  # noqa: E402
    _git_env,
    _commit,
    TRUST_KEY,
    REFUSAL_FILE,
    _read_base,
    trusted_base,
    _full,
    _is_ancestor,
    _set_base,
    trust_base,
    _no_base,
    _main_show,
    writers,
    _record_refusal,
    _kept_refusal,
    refusal,
    _mirror_ids,
    refusals,
    base_state,
    bases,
    _clear_refusal,
    _verify_incoming,
    FIRST_CONTACT_KEY,
    on_main,
    _taken,
    _take_verified,
)
from secretstore.entries import (  # noqa: E402
    init,
    _require_clean,
    _check_name,
    _one_line_off,
    _write_entry,
    _decrypt,
    _remote,
    _branch,
    _before_write,
    _push_if_ahead,
    _after_commit,
    stdin_value,
    set_entry,
    names,
    pull,
    values,
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
    return {"agent_id": agent_id, "mirror": mirror, "remote": remote}


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
    git(mirror, "fetch", "-q", "origin", "+main:refs/remotes/origin/main")
    _take_verified(mirror, "refs/remotes/origin/main", aid)
    return mirror


def take_bundle(text: str) -> dict:
    """The child fast-forwards its store from its parent's bundle, and
    only from one of its own store: the same agent id and the same key."""
    store = store_dir()
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
def lineage(fabric: str | None = None) -> dict:
    try:
        with open(os.path.join(keys_dir(fabric), "lineage.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise StoreError(f"identities/keys/lineage.json is not JSON: {e}") from None


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
        doc[aid] = {"login": name, "born": born_of(aid), "fingerprint": fpr, "parent": parent}
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
    """Every committed key against lineage.json, each on its own:
    - lineage: keyed by agent id (a UUIDv7), each naming a login no other
      agent has, a birth equal to its id's, exactly one root (parent
      null), nobody its own parent, every chain reaching that root;
    - `<id>.asc` holds exactly one primary key, the recorded one, with a
      valid user id addressed to that agent id;
    - a child's key carries a valid certification of that user id by its
      PARENT's recorded key, read in a keyring holding only the child's
      file and the parent's, so a certification found in another file, or
      a swapped or doubled file, never passes.
    Findings, one line each; [] is clean."""
    doc, kd, findings = lineage(fabric), keys_dir(fabric), []
    where = "identities/keys/lineage.json"
    if not os.path.isdir(kd):
        return []
    if not isinstance(doc, dict):
        return [f"{where}: not an object of agent id -> {{login, born, fingerprint, parent}}"]
    for who in [w for w, r in doc.items() if not isinstance(r, dict)]:
        findings.append(f"{where}: the entry for {who} is not an object")
        del doc[who]
    for who in [w for w in doc if not AGENT_ID_RE.match(w)]:
        findings.append(f"{where}: {who} is not an agent id (a UUIDv7, ADR-039)")
        del doc[who]
    logins: dict[str, str] = {}
    for who, rec in sorted(doc.items()):
        name = rec.get("login")
        if not isinstance(name, str) or not LOGIN_RE.match(name):
            findings.append(f"{where}: {who} has no login")
        elif name in logins:
            findings.append(f"{where}: {who} and {logins[name]} both have the login {name}")
        else:
            logins[name] = who
        if rec.get("born") != born_of(who):
            findings.append(f"{where}: {who}'s born is not its id's time ({born_of(who)})")
    files = {f[:-4] for f in os.listdir(kd) if f.endswith(".asc")}
    for extra in sorted(files - set(doc)):
        findings.append(f"identities/keys/{extra}.asc: no lineage.json entry")
    roots = sorted(w for w, r in doc.items() if r.get("parent") is None)
    if doc and len(roots) != 1:
        findings.append(f"{where}: {len(roots)} roots ({', '.join(roots) or 'none'}); "
                        "the chain has exactly one, the coordinator's key")
    for who, rec in sorted(doc.items()):
        parent = rec.get("parent")
        if parent == who:
            findings.append(f"{where}: {who} is its own parent")
            continue
        seen, at = {who}, parent
        while at is not None:
            if at in seen or at not in doc:
                findings.append(f"{where}: {who}'s chain "
                                + ("loops" if at in seen else f"names {at}, who has no entry") + "; it must reach the root")
                break
            seen.add(at)
            at = (doc.get(at) or {}).get("parent")

    def keyring_check(who: str, fpr: str, parent: str | None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            try:
                gpg("--import", os.path.join(kd, f"{who}.asc"), homedir=tmp, check=False)
                held = fingerprints(homedir=tmp)
                if held != [fpr]:
                    findings.append(f"identities/keys/{who}.asc: holds {len(held)} key(s), "
                                    f"{'not the recorded ' + fpr if fpr not in held else 'not only the recorded one'}")
                    return
                primary, subs = _key_caps(gpg("--with-colons", "--list-keys", fpr, homedir=tmp).stdout.decode())
                lacking = [name for cap, _, _, name in KEY_USES if cap not in subs]
                if lacking:
                    findings.append(f"identities/keys/{who}.asc: no {', '.join(lacking)} subkey; "
                                    "each use has its own key (ADR-038 rule 1)")
                if set(primary) & {"e", "a"}:
                    findings.append(f"identities/keys/{who}.asc: the primary key itself encrypts or authenticates; "
                                    "it certifies, and each use is a subkey (ADR-038 rule 1)")
                addr = f"<{who}@{UID_DOMAIN}>"
                if parent is not None:
                    pfpr = (doc.get(parent) or {}).get("fingerprint")
                    if not pfpr or parent not in files:
                        findings.append(f"identities/keys/{who}.asc: parent {parent} has no recorded, committed key")
                        return
                    gpg("--import", os.path.join(kd, f"{parent}.asc"), homedir=tmp, check=False)
                    if pfpr not in fingerprints(homedir=tmp):
                        findings.append(f"identities/keys/{parent}.asc: does not hold its recorded key")
                        return
                # Per user id: its validity, and the signatures made on it.
                r = gpg("--with-colons", "--check-sigs", fpr, homedir=tmp, check=False)
                on_id, has_id, certified = False, False, False
                for l in r.stdout.decode().splitlines():
                    f = l.split(":")
                    if f[0] == "uid":
                        on_id = f[1] not in ("r", "e", "i") and addr in f[9]
                        has_id |= on_id
                    elif f[0] in ("sub", "pub"):
                        on_id = False
                    elif f[0] == "sig" and on_id and parent is not None and f[1] == "!" and f[4] == pfpr[-16:]:
                        certified = True
                if not has_id:
                    findings.append(f"identities/keys/{who}.asc: no valid user id addressed to {who}")
                elif parent is not None and not certified:
                    findings.append(f"identities/keys/{who}.asc: not certified by its parent {parent}'s key")
            finally:
                _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)

    for who, rec in sorted(doc.items()):
        if who not in files:
            findings.append(f"{where}: {who} has no committed key")
            continue
        if rec.get("parent") == who:
            continue
        keyring_check(who, rec.get("fingerprint"), rec.get("parent"))
    return findings


# ── the Claude-account templates (ADR-031), in the coordinator's store ─
TEMPLATE_PREFIX = "CLAUDE_ACCOUNT_"
ASSIGNED_PREFIX = "CLAUDE_ASSIGNED_"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _slug_name(slug: str) -> str:
    if not SLUG_RE.match(slug):
        raise StoreError(f"{slug!r} is not an account slug (lowercase, digits, dashes)")
    return TEMPLATE_PREFIX + slug.upper().replace("-", "_")


def _assigned_name(agent_id: str) -> str:
    # Keyed by the agent id, as everything stored is (ADR-039): a rename
    # leaves the record the parent keeps for the agent where it was.
    return ASSIGNED_PREFIX + agent_id.replace("-", "").upper()


def _sha12(v: str) -> str:
    import hashlib
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def template_set(slug: str, value: bytes) -> dict:
    return set_entry(_slug_name(slug), value)


def templates() -> list[dict]:
    """Each template by its account and its token's fingerprint: the
    value goes into a hash and nowhere else."""
    vals = values()
    return [{"account": n[len(TEMPLATE_PREFIX):].lower().replace("_", "-"), "token_sha256_12": _sha12(v) if v else None}
            for n, v in sorted(vals.items()) if n.startswith(TEMPLATE_PREFIX)]


def assign(slug: str, logins: list[str], *, force: bool = False) -> list[dict]:
    """The template's token into each login's store, as its
    CLAUDE_CODE_OAUTH_TOKEN, written by the parent (which cannot read it
    back); the assignment is recorded in the parent's own store, since
    the parent cannot read the child's."""
    own = store_dir()
    _before_write(own)
    _push_if_ahead(own)   # a record an earlier failed push left behind
    vals = values()
    name = _slug_name(slug)
    if not vals.get(name):
        raise StoreError(f"{slug} is not a template in this store (fabric-secrets store templates)")
    rows = []
    fp = _sha12(vals[name])
    me = own_agent_id(own)
    for who in logins:
        # A login or an agent id, resolved first (ADR-039 rule 5); rows
        # name the agent by its login, the record keys it by its id.
        try:
            aid, lin = resolve(who)
        except StoreError as e:
            rows.append({"login": who, "from": "none", "status": "failed", "reason": str(e)[:160]})
            continue
        who, rec = lin.get("login") or who, _assigned_name(aid)
        # The parent's record is "<slug> <fingerprint>": the parent cannot
        # read the child's entry, so whether the child already holds this
        # token is decided here, by what the parent last wrote.
        was, _, was_fp = (vals.get(rec) or "none").partition(" ")
        if was == slug and was_fp == fp and not force:
            rows.append({"login": who, "from": was, "to": slug, "status": "unchanged", "token_sha256_12": fp})
            continue
        try:
            # The store's own agent has no mirror of itself under children/:
            # its token is its own entry, which it can also read back
            # (failed as "no store at …/children/<own id>", 2026-10-01).
            if aid == me:
                set_entry("CLAUDE_CODE_OAUTH_TOKEN", vals[name].encode(), exact=True)
            else:
                put(aid, "CLAUDE_CODE_OAUTH_TOKEN", vals[name].encode(), exact=True)
            set_entry(rec, f"{slug} {fp}".encode(), exact=True)
            rows.append({"login": who, "from": was, "to": slug, "status": "written", "token_sha256_12": fp})
        except StoreError as e:
            rows.append({"login": who, "from": was, "status": "failed", "reason": str(e)[:160]})
    return rows


# ── the owner's sheet ─────────────────────────────────────────────────
def _sheet_text() -> str:
    """The agent's secret key as paperkey text, with its revocation
    certificate and how to restore it: the recovery copy, whichever way
    it leaves the account."""
    if not shutil.which("paperkey"):
        raise StoreError("paperkey is not installed (runtime/provisioning/platform installs it)")
    fpr = key_of_store()
    secret = gpg("--export-secret-keys", fpr).stdout
    sheet = _run(["paperkey", "--output-type", "base16"], stdin=secret).stdout.decode()
    rev_path = os.path.join(os.environ.get("GNUPGHOME") or os.path.join(home(), ".gnupg"), "openpgp-revocs.d", f"{fpr}.rev")
    try:
        with open(rev_path, encoding="utf-8") as fh:
            revocation = fh.read()
    except OSError:
        revocation = "(no revocation certificate found; make one: gpg --gen-revoke " + fpr + ")\n"
    aid = own_agent_id()
    if not aid:
        # The restore line names identities/keys/<id>.asc; without an id it
        # would name a file that is never written.
        raise StoreError("this store has no agent id yet (store-enroll.sh): the sheet names the key by it")
    return (f"agent-fabric — the key of agent {aid} (login {login()} when written)\nfingerprint {fpr}\n\n"
            "Restore: paperkey --pubring <the committed identities/keys/"
            f"{aid}.asc> --secrets <this sheet> | gpg --import\n\n{sheet}\n{revocation}")


def paper(out: str | None = None) -> None:
    """The recovery copy to a terminal or a file, for the owner. Refused
    inside a model session: a secret is never shown to a model."""
    if os.environ.get("CLAUDECODE"):
        raise StoreError("refused inside a model session (CLAUDECODE is set): the owner runs this in a terminal; "
                         "recovery-copy writes the copy encrypted to the recovery key and prints only a path")
    if out is None and not sys.stdout.isatty():
        raise StoreError("stdout is not a terminal: pass --out FILE (written 0600) to print it from there")
    text = _sheet_text()
    if out:
        # O_NOFOLLOW: never through a symlink; fchmod: an existing file's
        # old mode never carries the key.
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


# ── Proton Drive: the stores' backup and the keys' recovery copies ─────
# The owner's decision (ADR-038 §7): a dedicated Proton account holds, in
# /my-files/agent-fabric/, every store as a git bundle (ciphertext only)
# with a manifest, and each key's recovery copy. The CLI's session is an
# entry of the running login's own store (PROTON_DRIVE_CREDENTIALS_STORE=
# pass over this store), so it is readable by this login alone; `auth
# login` is the owner's, in a terminal. Nothing here prints a value.
PROTON_ROOT = "/my-files/agent-fabric"


def _proton(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PASSWORD_STORE_DIR": store_dir(), "PROTON_DRIVE_CREDENTIALS_STORE": "pass"}
    exe = os.environ.get("PROTON_DRIVE_BIN") or shutil.which("proton-drive")
    if not exe:
        raise StoreError("the Proton Drive CLI is not installed (proton-drive in ~/.local/bin)")
    r = subprocess.run([exe, *args], capture_output=True, env=env, timeout=600)
    if check and r.returncode != 0:
        lines = [l for l in (r.stderr or r.stdout).decode(errors="replace").splitlines() if l.strip()]
        why = (lines or [f"exit {r.returncode}"])[-1]
        # The sign-in hint only when the CLI's own words are about signing
        # in: on any other error it would send the owner the wrong way.
        hint = (" (the session has lapsed: the owner runs `proton-drive auth login` with PASSWORD_STORE_DIR "
                "set to this store and PROTON_DRIVE_CREDENTIALS_STORE=pass)"
                if re.search(r"auth|session|log ?in|401|unauthori", why, re.I) else "")
        raise StoreError(f"proton-drive {args[0]} {args[1] if len(args) > 1 else ''}: {why}{hint}")
    return r


def _proton_folder(path: str) -> str:
    """The folder at path, made (with its parents) when absent. Asked with
    `info`, whose exit status says whether the node exists: `list` prints
    a decorated table, not paths, and reading it as paths made every run
    after the first try to create a folder that was there."""
    if path in ("", "/my-files"):
        # The drive's root always exists: failing on it is the session or
        # the network, said in the CLI's own words (and _proton's sign-in
        # hint), never a recursion past the root.
        _proton("filesystem", "info", "/my-files")
        return "/my-files"
    if _proton("filesystem", "info", path, check=False).returncode == 0:
        return path
    parent, name = path.rsplit("/", 1)
    _proton_folder(parent)
    _proton("filesystem", "create-folder", parent, name)
    return path


def _upload(local: str, folder: str) -> None:
    # A new revision, never a replacement: Proton keeps what was there.
    _proton("filesystem", "upload", "-f", "create-new-revision", "-t", local, folder)


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


RECOVERY_UID = f"agent-fabric recovery <recovery@{UID_DOMAIN}>"


def recovery_pub(fabric: str | None = None) -> str:
    return os.path.join(fabric or FABRIC_ROOT, "identities", "recovery.asc")


RECOVERY_MIN_PASSPHRASE = 12


def _read_recovery_passphrase() -> str:
    """Asked here, on the owner's terminal, never through gpg's pinentry:
    the first run left the prompt to the desktop's pinentry, the owner saw
    none, and the key was made with no private half kept anywhere."""
    import getpass
    first = getpass.getpass("recovery passphrase (only you keep it): ")
    if len(first) < RECOVERY_MIN_PASSPHRASE:
        raise StoreError(f"a recovery passphrase has at least {RECOVERY_MIN_PASSPHRASE} characters; nothing was made")
    if getpass.getpass("the same again: ") != first:
        raise StoreError("the two passphrases differ; nothing was made")
    return first


def _make_recovery_key(homedir: str, passphrase: str) -> tuple[str, str, str]:
    """The recovery key in homedir, every secret part protected by the
    passphrase (checked, not assumed); returns its fingerprint, its public
    half and its protected private half, both armoured."""
    base = ["gpg", "--homedir", homedir, "--batch", "--pinentry-mode", "loopback", "--passphrase-fd", "0"]
    def run(*a: str) -> bytes:
        return subprocess.run([*base, *a], input=passphrase.encode(), capture_output=True, check=True,
                              env={**os.environ, "GNUPGHOME": homedir}).stdout
    run("--quick-gen-key", RECOVERY_UID, "ed25519", "cert", "never")
    fpr = fingerprints(homedir=homedir, secret=True)[0]
    run("--quick-add-key", fpr, "cv25519", "encr", "never")
    info = subprocess.run(["gpg-connect-agent", "--homedir", homedir, "KEYINFO --list", "/bye"],
                          capture_output=True, text=True, check=True).stdout.split("\n")
    # KEYINFO: S KEYINFO <grip> <type> <serial> <idstr> <cached> <protection> …; P is protected.
    marks = [l.split()[7] for l in info if l.startswith("S KEYINFO")]
    if len(marks) != 2 or set(marks) != {"P"}:
        raise StoreError("the recovery key is not protected by the passphrase; nothing was published")
    public = gpg("--armor", "--export", fpr, homedir=homedir).stdout.decode()
    private = run("--armor", "--export-secret-keys", fpr).decode()
    if "BEGIN PGP PRIVATE KEY BLOCK" not in private:
        raise StoreError("the recovery key's private half did not export; nothing was published")
    return fpr, public, private


def recovery_key_init(force: bool = False) -> dict:
    """The owner's recovery key (ADR-038 §5 rule 1): made in a throwaway
    keyring, protected by a passphrase the owner types here; its protected
    private half uploaded to Proton (/my-files/agent-fabric/keys/
    recovery-key-<fpr16>.asc) and never kept on the host, and only then its public
    half written to identities/recovery.asc, so no agent can encrypt to a
    key whose private half is kept nowhere. Refused inside a model session:
    the passphrase is the owner's."""
    if os.environ.get("CLAUDECODE"):
        raise StoreError("refused inside a model session: the owner runs this in a terminal and types the passphrase")
    if not sys.stdin.isatty():
        raise StoreError("stdin is not a terminal: the owner types the passphrase")
    pub = recovery_pub()
    if os.path.exists(pub) and not force:
        raise StoreError(f"{pub} exists; a new recovery key is a rotation (--force), and every copy is then re-made")
    passphrase = _read_recovery_passphrase()
    old = _key_file_fingerprint(pub) if os.path.exists(pub) else None
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        try:
            fpr, public, private = _make_recovery_key(tmp, passphrase)
            # Named by its fingerprint, so the new key goes up beside the
            # old one: every step below that fails leaves recovery.asc
            # naming a key whose private half is in Proton. Deleting first
            # once risked the fleet's only recovery key on a failed upload.
            protected = os.path.join(tmp, _recovery_key_name(fpr))
            with open(protected, "w", encoding="utf-8") as fh:
                fh.write(private)
            _upload(protected, _proton_folder(f"{PROTON_ROOT}/keys"))
        finally:
            _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)
    with open(pub, "w", encoding="utf-8") as fh:
        fh.write(public)
    # The key rotated away is deleted, never kept as a revision; copies
    # still encrypted to it are unreadable from here until each agent's
    # recovery-copy re-makes its own (it sees the new recipient).
    if old and old != fpr:
        name = _recovery_key_name(old)
        if _proton("filesystem", "info", f"{PROTON_ROOT}/keys/{name}", check=False).returncode == 0:
            _proton("filesystem", "trash", f"{PROTON_ROOT}/keys/{name}")
            _proton("filesystem", "delete", f"/trash/{name}")
    return {"fingerprint": fpr, "public": pub, "private": f"{PROTON_ROOT}/keys/{_recovery_key_name(fpr)}"}


def _recovery_key_name(fpr: str) -> str:
    return f"recovery-key-{fpr[-16:]}.asc"


def recovery_copy(force: bool = False) -> dict:
    """This login's key recovery copy, encrypted to the owner's recovery
    key, committed into its own store as recovery/<agent id>.key.gpg and
    pushed; the parent's backup carries it to Proton. Nothing is printed
    but a path and a hash, and once written not even this login can read
    it back: only the owner, with the recovery passphrase."""
    pub = recovery_pub()
    if not os.path.exists(pub):
        raise StoreError("no recovery key yet (identities/recovery.asc): the owner runs `fabric-secrets store recovery-key init`")
    rfpr = _key_file_fingerprint(pub)
    store = store_dir()
    key_of_store(store)
    _require_clean(store)
    _before_write(store)
    aid = own_agent_id(store)
    if not aid:
        raise StoreError("this store has no agent id yet (store-enroll.sh)")
    path = os.path.join(store, "recovery", f"{aid}.key.gpg")
    note = os.path.join(store, "recovery", f"{aid}.recipient")
    if os.path.exists(path) and not force and open(note, encoding="utf-8").read().strip() == rfpr:
        _push_if_ahead(store)
        return {"path": path, "changed": False, "recipient": rfpr}
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", "--recipient-file", pub,
        "--output", path + ".tmp", stdin=_sheet_text().encode())
    os.replace(path + ".tmp", path)
    with open(note, "w", encoding="utf-8") as fh:
        fh.write(rfpr + "\n")
    git(store, "add", os.path.relpath(path, store), os.path.relpath(note, store))
    _commit(store, f"agent {login()}: recovery copy, encrypted to the recovery key {rfpr[-16:]}")
    _after_commit(store)
    return {"path": path, "changed": True, "recipient": rfpr}


def _stores() -> dict[str, str]:
    """This agent's own store and every child mirror it holds: agent id -> dir."""
    mine = own_agent_id()
    if not mine:
        raise StoreError("this store has no agent id yet (store-enroll.sh --self)")
    out = {mine: store_dir()}
    try:
        for child in sorted(os.listdir(children_dir())):
            d = os.path.join(children_dir(), child)
            if os.path.isdir(os.path.join(d, ".git")) and AGENT_ID_RE.match(child):
                out[child] = d
    except FileNotFoundError:
        pass
    return out


def backup() -> dict:
    """Every store this login holds — its own and its children's mirrors,
    each brought up to its remote first — as a git bundle (the whole
    history, ciphertext only), with a manifest of each bundle's sha256
    and head, uploaded to Proton Drive as new revisions."""
    folder = _proton_folder(f"{PROTON_ROOT}/secrets")
    import datetime
    manifest = {"written_by": login(), "stores": {}}
    manifest["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        for who, d in _stores().items():
            _before_write(d)
            bundle = os.path.join(tmp, f"{REPO_PREFIX}{who}.bundle")
            git(d, "bundle", "create", bundle, "--all")
            name = ((lineage().get(who) or {}).get("login")) or (login() if d == store_dir() else None)
            manifest["stores"][who] = {"bundle": os.path.basename(bundle), "sha256": _sha256_file(bundle), "login": name,
                                       "head": git(d, "rev-parse", "HEAD").stdout.decode().strip()}
            # Each store's recovery copy, already encrypted to the owner's
            # recovery key, also stands alone in keys/ for a restore.
            rdir = os.path.join(d, "recovery")
            for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
                if f.endswith(".key.gpg"):
                    manifest.setdefault("recovery_copies", {})[f] = _sha256_file(os.path.join(rdir, f))
                    _upload(os.path.join(rdir, f), _proton_folder(f"{PROTON_ROOT}/keys"))
        mpath = os.path.join(tmp, "manifest.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        for name in sorted(os.listdir(tmp)):
            _upload(os.path.join(tmp, name), folder)
    return manifest


def verify_backup() -> list[str]:
    """Download the manifest, every bundle and every recovery copy it
    names, and check each against its sha256 (and a bundle with `git
    bundle verify`). Findings; [] is clean."""
    folder = f"{PROTON_ROOT}/secrets"
    findings = []
    with tempfile.TemporaryDirectory() as tmp:
        # `git bundle verify` needs a repository around it: run from one
        # that is not, it failed every good bundle. An empty one of its own,
        # never the caller's cwd, which could be any repository or none.
        empty = os.path.join(tmp, ".verify-repo")
        os.makedirs(empty)
        git(empty, "init", "-q")
        _proton("filesystem", "download", "-f", "remove", f"{folder}/manifest.json", tmp)
        manifest = json.load(open(os.path.join(tmp, "manifest.json"), encoding="utf-8"))
        for who, rec in sorted(manifest.get("stores", {}).items()):
            _proton("filesystem", "download", "-f", "remove", f"{folder}/{rec['bundle']}", tmp)
            local = os.path.join(tmp, rec["bundle"])
            if _sha256_file(local) != rec["sha256"]:
                findings.append(f"{rec['bundle']}: its sha256 is not the manifest's")
                continue
            if _run(["git", "bundle", "verify", local], cwd=empty, check=False).returncode != 0:
                findings.append(f"{rec['bundle']}: git bundle verify fails")
        # The recovery copies stand alone in keys/ for a restore: each is
        # checked against the hash the manifest took when it went up.
        for f, sha in sorted((manifest.get("recovery_copies") or {}).items()):
            got = _proton("filesystem", "download", "-f", "remove", f"{PROTON_ROOT}/keys/{f}", tmp, check=False)
            local = os.path.join(tmp, f)
            if got.returncode != 0 or not os.path.exists(local):
                findings.append(f"keys/{f}: could not be downloaded")
            elif _sha256_file(local) != sha:
                findings.append(f"keys/{f}: its sha256 is not the manifest's")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets store", description="this agent's encrypted secrets (ADR-038)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--remote")
    i.add_argument("--agent-id", help="the id the parent minted at enrolment (store-enroll.sh)")
    s = sub.add_parser("set")
    s.add_argument("name")
    s.add_argument("--empty", action="store_true", help="store an empty value on purpose")
    n = sub.add_parser("names")
    n.add_argument("--json", action="store_true")
    p = sub.add_parser("put")
    p.add_argument("login")
    p.add_argument("name")
    p.add_argument("--store")
    p.add_argument("--empty", action="store_true", help="store an empty value on purpose")
    mi = sub.add_parser("mint-id", help="a new agent id whose time is the birth given")
    mi.add_argument("born", help='the birth: "now", ISO 8601, or as `stat -c %%w` prints it')
    sub.add_parser("id", help="this store's agent id")
    io = sub.add_parser("id-of", help="the agent id lineage.json records for a login")
    io.add_argument("login")
    rn = sub.add_parser("rename", help="a login renamed: its lineage entry, nothing else")
    rn.add_argument("old")
    rn.add_argument("new")
    c = sub.add_parser("certify")
    c.add_argument("login", nargs="?")
    c.add_argument("key_file", nargs="?")
    c.add_argument("--root", action="store_true")
    sub.add_parser("verify")
    tb = sub.add_parser("trust-base", help="the commit up to which this store's history is trusted unsigned (ADR-042)")
    tb.add_argument("commit", nargs="?")
    tb.add_argument("--store", help="a store other than this agent's own (a child's mirror)")
    sub.add_parser("export-key")
    sub.add_parser("push")
    sub.add_parser("bundle", help="this store, armored, for its parent (a new account's first contact)")
    sub.add_parser("take-bundle", help="fast-forward this store from its parent's bundle on stdin")
    sc = sub.add_parser("seed-child", help="a new child's bundle (stdin) becomes its mirror, pushed")
    sc.add_argument("agent_id")
    sc.add_argument("--remote", required=True)
    rm = sub.add_parser("refresh-mirror", help="a child's mirror brought up to its remote, every commit verified")
    rm.add_argument("login")
    cb = sub.add_parser("child-bundle", help="a child's store as its mirror holds it, armored")
    cb.add_argument("login")
    pa = sub.add_parser("paper")
    pa.add_argument("--out")
    rc = sub.add_parser("recovery-copy")
    rc.add_argument("--force", action="store_true", help="re-make it even when it is encrypted to the current recovery key")
    rk = sub.add_parser("recovery-key")
    rk.add_argument("action", choices=["init"])
    rk.add_argument("--force", action="store_true", help="rotate: a new recovery key; every copy is then re-made")
    bk = sub.add_parser("backup")
    bk.add_argument("--verify", action="store_true", help="download the backup and check it against its manifest")
    ts = sub.add_parser("template-set")
    ts.add_argument("slug")
    tl = sub.add_parser("templates")
    tl.add_argument("--json", action="store_true")
    asg = sub.add_parser("assign")
    asg.add_argument("slug")
    asg.add_argument("logins", nargs="+")
    asg.add_argument("--json", action="store_true")
    asg.add_argument("--force", action="store_true", help="write even when this store's record says unchanged")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "init":
            r = init(args.remote, args.agent_id)
            print(f"store: {r['store']}  agent: {r['agent_id']}  key: {r['fingerprint']}{' (made)' if r['key_made'] else ''}"
                  + (f"  subkeys added: {', '.join(r['subkeys_added'])}" if r['subkeys_added'] and not r['key_made'] else ""))
        elif args.cmd == "mint-id":
            print(mint_agent_id(born_ms_of(args.born)))
        elif args.cmd == "id":
            # 3 is "no id yet", the one answer that lets a parent mint; any
            # other failure (no store read, a malformed .agent-id) is 1.
            aid = own_agent_id()
            if not aid:
                print("fabric-secrets store: this store has no agent id yet", file=sys.stderr)
                return 3
            print(aid)
        elif args.cmd == "id-of":
            # 3, as `id` answers "no id yet": no agent with that login. A
            # lineage that cannot be read is 1, never a reason to mint.
            try:
                print(resolve(args.login)[0])
            except NotInLineage as e:
                print(f"fabric-secrets store: {e}", file=sys.stderr)
                return 3
        elif args.cmd == "rename":
            r = rename(args.old, args.new)
            print(f"agent {r['agent_id']}: now {r['login']}")
        elif args.cmd == "set":
            r = set_entry(args.name, stdin_value(args.empty))
            print(f"{args.name}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "names":
            ns = names()
            print(json.dumps(ns) if args.json else "\n".join(ns) or "(no entries)")
        elif args.cmd == "put":
            r = put(args.login, args.name, stdin_value(args.empty), store=args.store)
            print(f"{args.login} {args.name}: {'written' if r['changed'] else 'unchanged'}")
        elif args.cmd == "certify":
            if args.root == bool(args.login):
                raise StoreError("certify takes LOGIN KEYFILE, or --root for this login's own key")
            if args.login and not args.key_file:
                raise StoreError("certify LOGIN needs the child's exported public key file")
            r = certify(None if args.root else args.login, args.key_file)
            print(f"{r['login']} ({r['agent_id']}): {r['fingerprint']}, parent {r['parent'] or '(root)'}")
        elif args.cmd == "export-key":
            sys.stdout.write(export_key())
        elif args.cmd == "refresh-mirror":
            print(f"mirror up to date: {refresh_mirror(args.login)}")
        elif args.cmd == "trust-base":
            r = trust_base(args.commit, args.store)
            print(f"trusted base: {r['trusted_base']}" + (f" (was {r['was']})" if r["was"] and r["was"] != r["trusted_base"] else ""))
        elif args.cmd == "push":
            store = store_dir()
            key_of_store(store)
            if not git(store, "remote", check=False).stdout.strip():
                raise StoreError("the store has no remote (fabric-secrets store init --remote URL)")
            # What the parent put since is taken first, only as a fast-forward:
            # a re-enrolment after a put pushed the account's older head and
            # was refused as non-fast-forward. A new repository has no main.
            git(store, "fetch", "-q", "origin")
            if git(store, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False).returncode == 0:
                _take_verified(store, "refs/remotes/origin/main")
            git(store, "push", "-q", "-u", "origin", "HEAD:main")
            print("pushed")
        elif args.cmd == "bundle":
            sys.stdout.write(bundle_own())
        elif args.cmd == "take-bundle":
            r = take_bundle(sys.stdin.read())
            print(f"taken: agent {r['agent_id']} at {r['head']}, {r['names']} entries")
        elif args.cmd == "seed-child":
            r = seed_child(args.agent_id, args.remote, sys.stdin.read())
            print(f"seeded: agent {r['agent_id']}, mirror {r['mirror']}, pushed to {r['remote']}")
        elif args.cmd == "child-bundle":
            sys.stdout.write(child_bundle(args.login))
        elif args.cmd == "verify":
            f = verify()
            print("\n".join(f) if f else "keys: clean")
            return 1 if f else 0
        elif args.cmd == "paper":
            paper(args.out)
        elif args.cmd == "recovery-copy":
            r = recovery_copy(args.force)
            print(f"{r['path']}: {'written' if r['changed'] else 'unchanged'}, encrypted to the recovery key {r['recipient'][-16:]}")
        elif args.cmd == "recovery-key":
            r = recovery_key_init(args.force)
            print(f"recovery key {r['fingerprint']}: public half {r['public']} (commit it), protected private half {r['private']}")
        elif args.cmd == "backup":
            if args.verify:
                f = verify_backup()
                print("\n".join(f) if f else "backup: every bundle and recovery copy matches its manifest")
                return 1 if f else 0
            m = backup()
            for who, rec in sorted(m["stores"].items()):
                print(f"{PROTON_ROOT}/secrets/{rec['bundle']}  sha256 {rec['sha256'][:16]}…  head {rec['head'][:12]}")
        elif args.cmd == "template-set":
            r = template_set(args.slug, sys.stdin.buffer.read())
            print(f"template {args.slug}: {'set' if r['changed'] else 'unchanged'}")
        elif args.cmd == "templates":
            t = templates()
            if args.json:
                print(json.dumps(t))
            else:
                print("\n".join(f"{x['account']:<34} setup-token {x['token_sha256_12']}" for x in t) or "(no templates)")
        elif args.cmd == "assign":
            rows = assign(args.slug, args.logins, force=args.force)
            if args.json:
                print(json.dumps(rows))
            else:
                for r in rows:
                    print(f"{r['login']:<22} {r['from']:<30} -> {r.get('to', '-'):<30} {r['status']}{('  ' + r['reason']) if r.get('reason') else ''}")
            return 0 if all(r["status"] != "failed" for r in rows) else 1
    except StoreError as e:
        print(f"fabric-secrets store: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
