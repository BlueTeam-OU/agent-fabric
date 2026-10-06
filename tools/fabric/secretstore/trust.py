"""tools/fabric/secretstore/trust.py — who may write a store (ADR-042): signed commits, the trusted base, writers, and refusals.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from typing import TypedDict

from .core import (
    FABRIC_ROOT,
    UID_DOMAIN,
    StoreError,
    login,
    AGENT_ID_RE,
    own_agent_id,
    store_dir,
    children_dir,
    _run,
    _failure,
    gpg,
    git,
)
from .keys import key_of_store, _signing_args, _signing_subkeys



# The records status, fabric-ctl keys and the drain read. The optional keys
# live in a total=False subclass: under `from __future__ import annotations`
# TypedDict counts a NotRequired[...] key as required. tests/test_types.py
# holds both to the values built here.
class _RefusalKeys(TypedDict):
    reason: str


class RefusalRecord(_RefusalKeys, total=False):
    """A store's last refusal (ADR-042 rule 5): the commit and when, as
    _record_refusal writes it; or a record that could not be read
    (unreadable, with why). refusals() names the store it is of."""
    commit: str
    at: str
    unreadable: bool
    store: str


class _BaseKeys(TypedDict):
    state: str


class BaseRecord(_BaseKeys, total=False):
    """A store with no trusted base: "no base", or "unreadable" with why.
    bases() names the store and its path."""
    reason: str
    store: str
    path: str

def _git_env() -> dict:
    """The store's own identity for every commit it makes, a rebase's
    included: the writing login, whatever the account's git config says
    (a new account may have none yet), addressed by its agent id once
    it has one, as its key is."""
    try:
        addr = f"{own_agent_id() or login()}@{UID_DOMAIN}"
    except StoreError:
        addr = f"{login()}@{UID_DOMAIN}"
    return {**os.environ, "GIT_AUTHOR_NAME": login(), "GIT_AUTHOR_EMAIL": addr,
            "GIT_COMMITTER_NAME": login(), "GIT_COMMITTER_EMAIL": addr}


def _commit(store: str, message: str) -> None:
    # The store's commits are its own history, attributed by message:
    # the writer ("agent <login>" or "parent <login>") and what changed,
    # never a value. Signed with the writer's own key (ADR-042 rule 1): a
    # writer that cannot sign does not write — and leaves nothing staged:
    # an entry left in the index made every later set, pull and sync fail
    # on the dirty store (review of ADR-042, F2). Back to HEAD, or, on a
    # store with no commit yet, unstaged. The reset discards every tracked
    # change, so each writer starts from a clean store (_require_clean).
    # "could not sign" only when signing is what failed — the key not
    # found, or git saying gpg failed: a hook or a lock is another failure
    # (review of #94). git's own words are read in the C locale.
    try:
        signing = _signing_args()
    except StoreError as e:
        failed, what = e, "could not sign the commit"
    else:
        r = _run(["git", "-C", store, *signing, "commit", "-q", "-m", message],
                 env={**_git_env(), "LC_ALL": "C"}, check=False)
        if r.returncode == 0:
            return
        failed = _failure("git commit", r)
        what = "could not sign the commit" if b"failed to sign the data" in r.stderr else "could not commit"
    unborn = git(store, "rev-parse", "-q", "--verify", "HEAD", check=False).returncode != 0
    r = git(store, "rm", "-r", "-q", "--cached", ".", check=False) if unborn else \
        git(store, "reset", "-q", "--hard", "HEAD", check=False)
    if r.returncode != 0:
        why = ([l for l in r.stderr.decode(errors="replace").splitlines() if l.strip()] or [f"exit {r.returncode}"])[-1]
        raise StoreError(f"{what} ({failed}); and {store} could not be reset ({why}) "
                         "— reset it before the next write") from failed
    raise StoreError(f"{what} ({failed}); nothing written") from failed


# ── who may write a store (ADR-042) ───────────────────────────────────
# Every commit to a store is signed by its writer: the agent's own key in
# its store, the parent's own key in the mirror of a child's — always the
# key of the account running this, key_of_store(store_dir()). A store takes
# in only commits signed by a signing subkey of its writers: the agent's
# own primary key and its recorded parent's (the root agent: its own
# alone), read with `git show` at the fabric checkout's origin/main, never
# its working tree, so an uncommitted edit names no writer. History the
# store held before the decision is trusted once, at its trusted base:
# agent-fabric.trustedbase in the store's own .git/config, never in a
# commit, which the remote could write. `store trust-base` records it (the
# migration, run once per store; a new store's init records its own first
# commit), and a verified fetch moves it forward to what it verified. A
# store with no base verifies nothing, and so takes nothing in.
TRUST_KEY = "agent-fabric.trustedbase"
REFUSAL_FILE = "agent-fabric-refusal.json"


def _read_base(store: str) -> tuple[str | None, str | None]:
    """(the base, None), (None, None) when there is none, or (None, why)
    when the store's config cannot be read. --local: a plain get also read
    ~/.gitconfig, the system's and GIT_CONFIG_* from the environment, and a
    base set there trusted every store. The config is opened first: git
    reads one it cannot open as one without the key (exit 1, a warning),
    which would say "no base" for "unreadable"."""
    try:
        with open(os.path.join(store, ".git", "config"), "rb"):
            pass
    except OSError as e:
        return None, f".git/config could not be read ({type(e).__name__})"
    r = git(store, "config", "--local", "--get", TRUST_KEY, check=False)
    if r.returncode not in (0, 1):
        return None, str(_failure(".git/config", r))
    v = r.stdout.decode().strip()
    return (v if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", v) else None), None


def trusted_base(store: str) -> str | None:
    return _read_base(store)[0]


def _full(store: str, rev: str) -> str:
    r = git(store, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}", check=False)
    if r.returncode != 0:
        raise StoreError(f"{rev} is no commit in {store}")
    return r.stdout.decode().strip()


def _is_ancestor(store: str, older: str, newer: str) -> bool:
    return git(store, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def _set_base(store: str, commit: str) -> None:
    git(store, "config", TRUST_KEY, commit)


def trust_base(commit: str | None = None, store: str | None = None) -> dict:
    """The store's trusted base: the commit up to which its history is taken
    unsigned (ADR-042 rule 4). Set once — the migration — and only ever
    moved forward: a base that is not a descendant of the one recorded is
    refused, never a way to trust more of the past."""
    store = store or store_dir()
    key_of_store(store)
    new = _full(store, commit or "HEAD")
    if not _is_ancestor(store, new, "HEAD"):
        raise StoreError(f"{new[:12]} is not in this store's history; a base is a commit the store already holds")
    old = trusted_base(store)
    if old and not _is_ancestor(store, old, new):
        raise StoreError(f"the trusted base is {old[:12]}; {new[:12]} does not follow it, and a base only moves forward")
    _set_base(store, new)
    return {"store": store, "trusted_base": new, "was": old}


def _no_base(store: str) -> StoreError:
    return StoreError(f"{store} has no trusted base, so nothing it is given can be verified (ADR-042): "
                      "fabric-secrets store trust-base, once, at the head it holds")


def _main_show(rel: str, fabric: str | None = None) -> bytes | None:
    """A file as the fabric's origin/main has it; None when main has no such
    file. A checkout with no origin/main is an error, never a fallback."""
    root = fabric or FABRIC_ROOT
    if _run(["git", "-C", root, "rev-parse", "-q", "--verify", "refs/remotes/origin/main"], check=False).returncode:
        raise StoreError(f"{root} has no origin/main to read the store's writers from: fetch the fabric")
    r = _run(["git", "-C", root, "show", f"refs/remotes/origin/main:{rel}"], check=False)
    return r.stdout if r.returncode == 0 else None


def writers(agent_id: str, fabric: str | None = None) -> dict[str, bytes]:
    """{primary fingerprint: its armored public key} for the keys allowed to
    write this agent's store (ADR-042 rule 2), from the fabric's main."""
    raw = _main_show("identities/keys/lineage.json", fabric)
    try:
        doc = json.loads(raw) if raw is not None else {}
    except ValueError as e:
        raise StoreError(f"identities/keys/lineage.json on origin/main is not JSON: {e}") from None
    rec = doc.get(agent_id) if isinstance(doc, dict) else None
    if not isinstance(rec, dict):
        raise StoreError(f"agent {agent_id} is not yet on the fabric's main (lineage.json at origin/main): "
                         "its writers cannot be known — fetch the fabric")
    out: dict[str, bytes] = {}
    for who in [agent_id] + ([rec["parent"]] if rec.get("parent") else []):
        r = doc.get(who) if isinstance(doc.get(who), dict) else {}
        fpr, key = r.get("fingerprint"), _main_show(f"identities/keys/{who}.asc", fabric)
        if not fpr or key is None:
            raise StoreError(f"agent {who}'s key is not yet on the fabric's main: fetch the fabric")
        out[fpr] = key
    return out


def _record_refusal(store: str, commit: str, reason: str) -> None:
    """A refusal is a security event (ADR-042 rule 5): it is kept beside the
    store until a verified fetch succeeds, for status and fabric-ctl keys."""
    import datetime
    path = os.path.join(store, ".git", REFUSAL_FILE)
    # A temporary name of its own: two runs refusing on one store at once
    # must not write through each other's half-written file.
    fd, tmp = tempfile.mkstemp(prefix=REFUSAL_FILE + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"commit": commit, "reason": reason,
                       "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _kept_refusal(store: str) -> str | None:
    """Where a child's mirror's refusal is kept once the mirror is gone:
    beside it, as its lock is, so removing the mirror leaves it. None for a
    store that is no mirror."""
    store = os.path.normpath(store)
    return store + ".refusal.json" if os.path.dirname(store) == os.path.normpath(children_dir()) else None


def refusal(store: str | None = None) -> RefusalRecord | None:
    """The store's last refusal, or None when it has no record. A record
    that cannot be read or parsed is no clean bill: it comes back marked
    unreadable, and status stays non-OK on it (review of #94). A mirror
    with no record of its own is read beside it (_kept_refusal)."""
    store = store or store_dir()
    try:
        try:
            fh = open(os.path.join(store, ".git", REFUSAL_FILE), encoding="utf-8")
        except FileNotFoundError:
            kept = _kept_refusal(store)
            if kept is None:
                raise
            fh = open(kept, encoding="utf-8")
        with fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        return {"unreadable": True, "reason": f"{REFUSAL_FILE} could not be read ({type(e).__name__})"}
    return doc if isinstance(doc, dict) else {"unreadable": True, "reason": f"{REFUSAL_FILE} is not a JSON object"}


def _mirror_ids(*, kept: bool = False) -> list[str]:
    """The agent ids of the children's mirrors this account holds; kept:
    also those whose mirror is gone and whose refusal is kept beside it. No
    children directory is none; one that cannot be listed is an error, never
    an empty answer: status would read clean on it (review of #94)."""
    try:
        names = os.listdir(children_dir())
        ids = {n for n in names if AGENT_ID_RE.match(n)}
        if kept:
            ids |= {n[:-len(".refusal.json")] for n in names
                    if n.endswith(".refusal.json") and AGENT_ID_RE.match(n[:-len(".refusal.json")])}
        return sorted(ids)
    except FileNotFoundError:
        return []
    except OSError as e:
        raise StoreError(f"{children_dir()} could not be listed ({type(e).__name__})") from None


def refusals() -> list[RefusalRecord]:
    """Every refusal this account holds, each named: its own store's
    ("store": "own") and each child's mirror's ("store": the child's agent
    id). A mirror's refusal is the parent's to repair, and was said nowhere
    while only the own store was read (review of ADR-042, F3)."""
    out = []
    own = refusal()
    if own:
        out.append({**own, "store": "own"})
    for aid in _mirror_ids(kept=True):
        r = refusal(os.path.join(children_dir(), aid))
        if r:
            out.append({**r, "store": aid})
    return out


def base_state(store: str) -> BaseRecord | None:
    """None when the store has a trusted base; else its state, in the names
    fabric-ctl keys uses: "no base", or "unreadable" with why. Read as the
    verifier reads it (_read_base), so status cannot disagree with it."""
    base, why = _read_base(store)
    if why:
        return {"state": "unreadable", "reason": why}
    return None if base else {"state": "no base"}


def bases() -> list[BaseRecord]:
    """Every store this account holds that has no trusted base, and so
    refuses every verified operation (ADR-042): its own ("store": "own"),
    when there is one, and each child's mirror ("store": the agent id),
    with its path. Said by status as a refusal is (review of #94). The own
    store is read when its directory exists at all, not when its .git does:
    a store whose .git is gone still has every env/*.gpg status checks, and
    status read OK on it with no repository and no base (#96 review)."""
    out = []
    own = store_dir()
    stores = ([("own", own)] if os.path.lexists(own) else []) + \
        [(aid, os.path.join(children_dir(), aid)) for aid in _mirror_ids()]
    for name, path in stores:
        st = base_state(path)
        if st:
            out.append({**st, "store": name, "path": path})
    return out


def _clear_refusal(store: str) -> None:
    for path in filter(None, (os.path.join(store, ".git", REFUSAL_FILE), _kept_refusal(store))):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _verify_incoming(store: str, tip: str, agent_id: str | None = None, fabric: str | None = None,
                     *, from_root: bool = False) -> str:
    """Every commit `tip` would bring that the store neither holds nor trusts
    (tip, not HEAD, not the base), each signed by a writer of this agent's
    store (ADR-042 rule 3). Any other refuses the whole operation: nothing
    is applied, the refusal is recorded and names the commit and why, never
    an entry. from_root: every commit of tip's history, for a store that
    holds nothing and trusts nothing yet. Returns the verified tip's full id."""
    base = trusted_base(store)
    if not base and not from_root:
        raise _no_base(store)
    tip = _full(store, tip)
    revs = git(store, "rev-list", "--reverse", tip, *([] if from_root else ["^HEAD", f"^{base}"])).stdout.decode().split()
    if not revs:
        return tip
    aid = agent_id or own_agent_id(store)

    def refuse(commit: str, reason: str) -> StoreError:
        _record_refusal(store, commit, reason)
        return StoreError(f"commit {commit[:12]} refused: {reason}; nothing applied (ADR-042) — "
                          "the store's parent or the owner repairs it")
    try:
        allowed = writers(aid, fabric)
    except StoreError as e:
        # The writers are not known yet (a new child before its keys merge,
        # a fabric not fetched): the operation stops, nothing applied, but
        # nothing was shown wrong with the commit — no refusal recorded, no
        # security event said until a repair (review of ADR-042).
        raise StoreError(f"{e}; nothing applied") from None
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        try:
            for key in allowed.values():
                gpg("--import", stdin=key, homedir=tmp)
            subkeys = _signing_subkeys(tmp)
            env = {**os.environ, "GNUPGHOME": tmp}
            for c in revs:
                r = _run(["git", "-C", store, "-c", "gpg.program=gpg", "verify-commit", "--raw", c], env=env, check=False)
                status = [l.split() for l in r.stderr.decode(errors="replace").splitlines() if l.startswith("[GNUPG:] ")]
                tags = {f[1] for f in status if len(f) > 1}
                valid = next((f for f in status if len(f) > 2 and f[1] == "VALIDSIG"), None)
                if tags & {"EXPKEYSIG", "REVKEYSIG", "BADSIG", "EXPSIG"}:
                    bad = sorted(tags & {"EXPKEYSIG", "REVKEYSIG", "BADSIG", "EXPSIG"})[0]
                    raise refuse(c, {"BADSIG": "its signature does not verify", "EXPSIG": "its signature has expired",
                                     "EXPKEYSIG": "signed by an expired key", "REVKEYSIG": "signed by a revoked key"}[bad])
                if not valid:
                    raise refuse(c, "signed by a key that is no writer of this store on the fabric's main "
                                    "(a new or rotated key not yet merged: fetch the fabric)" if "ERRSIG" in tags
                                    or "NO_PUBKEY" in tags else "not signed")
                signer, primary = valid[2], valid[-1]
                # Defence in depth, not dead code: gpg already refuses a
                # signature by a key that is no signing key of its primary,
                # and the keyring holds only writers' keys, so no test can
                # make this fail today (its mutation survives). It holds the
                # rule should gpg's behaviour or the keyring's contents change.
                if primary not in allowed or subkeys.get(signer) != primary:
                    raise refuse(c, f"signed by {signer[-16:]}, no signing key of this store's writers")
        finally:
            _run(["gpgconf", "--homedir", tmp, "--kill", "all"], check=False)
    return tip


FIRST_CONTACT_KEY = "agent-fabric.firstcontact"


def on_main(agent_id: str, fabric: str | None = None) -> bool:
    """Whether the fabric's main records this agent (its keys PR merged)."""
    raw = _main_show("identities/keys/lineage.json", fabric)
    try:
        doc = json.loads(raw) if raw is not None else {}
    except ValueError as e:
        raise StoreError(f"identities/keys/lineage.json on origin/main is not JSON: {e}") from None
    return isinstance(doc, dict) and isinstance(doc.get(agent_id), dict)


def _taken(store: str, tip: str) -> None:
    """What a verified fetch applied moves the trusted base forward to it,
    and a refusal recorded earlier is over: the store took a verified head."""
    base = trusted_base(store)
    if base and _is_ancestor(store, base, tip) and _is_ancestor(store, tip, "HEAD"):
        _set_base(store, tip)
    _clear_refusal(store)


def _take_verified(store: str, ref: str, agent_id: str | None = None) -> str:
    """`ref` verified, then taken as a fast-forward only (ADR-042 rule 3)."""
    tip = _verify_incoming(store, ref, agent_id)
    git(store, "merge", "-q", "--ff-only", tip)
    _taken(store, tip)
    return tip
