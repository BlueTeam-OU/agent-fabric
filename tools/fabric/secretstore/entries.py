"""tools/fabric/secretstore/entries.py — the store's own entries: init, set, names, values and pull, and the write path around them.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import os
import subprocess
import sys

from .core import NAME_RE, UID_DOMAIN, StoreError, login, AGENT_ID_RE, own_agent_id, store_dir, _run, gpg, git
from .keys import fingerprints, key_of_store, _ensure_use_subkeys, uid_of, _signing_args
from .trust import _git_env, _commit, trusted_base, _full, _set_base, _verify_incoming, _taken
from .lock import write_lock, require_write_lock


def init(remote: str | None = None, agent_id: str | None = None) -> dict:
    """The agent's key (made here, with no passphrase: agents decrypt
    unattended) and its store, under the agent id its parent minted.
    Idempotent: an existing key, store or id is kept, never replaced; a
    key made before ids existed gains the id's user id."""
    me, store = login(), store_dir()
    held = own_agent_id(store) if os.path.isdir(store) else None
    if held and agent_id and held != agent_id:
        raise StoreError(f"this store is agent {held}; an agent id is never replaced")
    aid = held or agent_id
    if not aid or not AGENT_ID_RE.match(aid):
        raise StoreError("no agent id: the parent mints it at enrolment (store-enroll.sh), and init takes --agent-id")
    uid = uid_of(aid, me)
    gpg_id = os.path.join(store, ".gpg-id")
    fpr = key_of_store(store) if os.path.exists(gpg_id) else next(iter(fingerprints(secret=True, query=f"<{aid}@{UID_DOMAIN}>")), None)
    made = False
    if not fpr:
        gpg("--quick-gen-key", uid, "ed25519", "cert", "never")
        fpr = fingerprints(secret=True, query=f"={uid}")[0]
        made = True
    elif fpr not in fingerprints(secret=True, query=f"<{aid}@{UID_DOMAIN}>"):
        gpg("--quick-add-uid", fpr, uid)
    # A key made before the split gains the subkeys it lacks, and keeps its
    # fingerprint: its parent re-exports it at the next certification.
    added = _ensure_use_subkeys(fpr)
    os.makedirs(os.path.join(store, "env"), mode=0o700, exist_ok=True)
    if not os.path.isdir(os.path.join(store, ".git")):
        git(store, "init", "-q", "-b", "main")
    # Locked from here: the steps above make the key and .git, each
    # idempotent, and a lock needs the .git it lives in.
    with write_lock(store):
        # Keyed on a first commit, not on a new .git: an init whose first commit
        # failed (no signing key yet) leaves .git behind, and its retry must
        # still record the base (review of ADR-042, F2).
        first = git(store, "rev-parse", "-q", "--verify", "HEAD", check=False).returncode != 0
        if not first:
            _require_clean(store)
        with open(gpg_id, "w", encoding="utf-8") as fh:
            fh.write(fpr + "\n")
        with open(os.path.join(store, ".agent-id"), "w", encoding="utf-8") as fh:
            fh.write(aid + "\n")
        git(store, "add", ".gpg-id", ".agent-id")
        if git(store, "diff", "--cached", "--quiet", check=False).returncode:
            _commit(store, f"agent {me} ({aid}): the store is encrypted to {fpr}")
        if first and trusted_base(store) is None:
            # A store made here starts from its own signed commit: its trusted
            # base, so it verifies what it is given from the first fetch on.
            # A store that held history before keeps the explicit trust-base.
            _set_base(store, _full(store, "HEAD"))
        if remote:
            if git(store, "remote", check=False).stdout.strip():
                git(store, "remote", "set-url", "origin", remote)
            else:
                git(store, "remote", "add", "origin", remote)
        return {"login": me, "agent_id": aid, "fingerprint": fpr, "key_made": made, "store": store, "subkeys_added": added}


def _require_clean(store: str) -> None:
    """A write starts from a store with no uncommitted change to a tracked
    file: a failed write is undone by a reset to the last commit (_commit,
    and put's reset to the remote), which would take such a change with it
    (review of #94). Untracked files are no part of it: a reset leaves them."""
    dirty = git(store, "status", "--porcelain", "--untracked-files=no").stdout.decode(errors="replace").splitlines()
    if dirty:
        more = f" and {len(dirty) - 1} more" if len(dirty) > 1 else ""
        raise StoreError(f"{store} has uncommitted changes ({dirty[0][3:]}{more}); nothing written — "
                         "a write starts from a clean store, since a failed one is undone by a reset")


def _check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise StoreError(f"{name!r} is not a secret name (UPPER_SNAKE, as an environment variable)")


def _one_line_off(value: bytes) -> bytes:
    """A value typed or piped on stdin: one trailing newline is the
    terminal's, not the secret's."""
    return value[:-1] if value.endswith(b"\n") else value


def _write_entry(store: str, name: str, value: bytes, recipient_args: list[str]) -> str:
    """The value EXACTLY as given, multi-line and empty included: sync
    must apply every value as it was set (a PEM key is many lines). A single-line value is pass's shape as it is: the
    secret on the first line. --no-encrypt-to: a gpg.conf naming an extra
    recipient never adds one."""
    _check_name(name)
    path = os.path.join(store, "env", f"{name}.gpg")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", *recipient_args, "--output", path + ".tmp",
        stdin=value)
    os.replace(path + ".tmp", path)
    git(store, "add", os.path.relpath(path, store))
    return path


def _decrypt(path: str) -> bytes | None:
    """The value as stored, bytes: an own entry may hold any bytes, and a
    decode here once made set of a non-UTF-8 value fail with a traceback
    naming one of its bytes (review of the own-secrets PR)."""
    r = gpg("--decrypt", path, check=False)
    return r.stdout if r.returncode == 0 else None


def _remote(store: str) -> bool:
    return bool(git(store, "remote", check=False).stdout.strip())


def _branch(store: str) -> str:
    return git(store, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.decode().strip() or "main"


def _before_write(store: str) -> None:
    """The store is brought up to its remote before anything is written:
    the agent and its parent both write, and a write on a stale copy is a
    divergence. One file per entry, so a rebase never conflicts on two
    different names. A failure stops the write, loudly."""
    require_write_lock(store)
    if not _remote(store):
        return
    branch = _branch(store)

    def failed(r: subprocess.CompletedProcess) -> StoreError:
        lines = [l for l in r.stderr.decode(errors="replace").splitlines() if l.strip() and not l.startswith("hint:")]
        return StoreError("the store could not be brought up to its remote; nothing written: " + (lines or ["?"])[-1])
    r = _run(["git", "-C", store, "fetch", "-q", "origin", f"+{branch}:refs/remotes/origin/{branch}"],
             env=_git_env(), check=False)
    if r.returncode != 0:
        raise failed(r)
    # Verified before anything is applied (ADR-042 rule 3): what the remote
    # added since, each commit signed by a writer; then this store's own
    # unpushed commits go on top, signed again by their writer.
    tip = _verify_incoming(store, f"refs/remotes/origin/{branch}")
    r = _run(["git", "-C", store, *_signing_args(), "rebase", "-q", tip], env=_git_env(), check=False)
    if r.returncode != 0:
        _run(["git", "-C", store, "rebase", "--abort"], check=False)
        raise failed(r)
    _taken(store, tip)


def _push_if_ahead(store: str) -> None:
    """A commit an earlier, failed push left behind is pushed now, so a
    retry that finds nothing to change still leaves the remote (the
    backup) whole. Only a store's own writer calls this — the agent in its
    store, the parent in its own — never a parent on a child's mirror."""
    ahead = git(store, "rev-list", "--count", f"origin/{_branch(store)}..HEAD", check=False)
    if _remote(store) and ahead.returncode == 0 and ahead.stdout.decode().strip() not in ("", "0"):
        _after_commit(store)


def _after_commit(store: str) -> None:
    """Every commit reaches the remote: it is the backup and the channel
    between the agent and its parent."""
    if _remote(store):
        git(store, "push", "-q", "origin", f"HEAD:{_branch(store)}")


def stdin_value(allow_empty: bool, name: str = "the value") -> bytes:
    """A value from stdin, refused when it is empty and not meant to be: a
    pipe whose producer failed reaches here as nothing, and stored it reads
    "set" while the login now holds an empty token, which the launcher
    refuses at the next session (devex-tooling, 2026-10-01). One trailing
    newline is not a value either. A terminal is asked twice without echo,
    as the recovery passphrase is: read from a tty, the value was echoed
    onto the screen and into its scrollback."""
    if sys.stdin.isatty():
        import getpass
        first = getpass.getpass(f"{name} (not echoed): ")
        if getpass.getpass("the same again: ") != first:
            raise StoreError("the two entries differ; nothing written")
        value = first.encode()
    else:
        value = sys.stdin.buffer.read()
    if not allow_empty and not _one_line_off(value):
        raise StoreError("no value on stdin — nothing written (an empty value on purpose: --empty)")
    return value


def set_entry(name: str, value: bytes, *, exact: bool = False) -> dict:
    """The agent writes its own entry. From stdin one trailing newline is
    dropped (exact=False); an in-process caller passes the value as it
    is. GPG encryption is randomised, so "unchanged" is decided on the
    decrypted value, which the agent can read (a parent cannot: see assign)."""
    store = store_dir()
    with write_lock(store):
        fpr = key_of_store(store)
        _check_name(name)
        value = value if exact else _one_line_off(value)
        _require_clean(store)
        _before_write(store)
        path = os.path.join(store, "env", f"{name}.gpg")
        if os.path.exists(path) and _decrypt(path) == value:
            _push_if_ahead(store)   # unchanged, but an earlier failed push is caught up
            return {"name": name, "changed": False}
        _write_entry(store, name, value, ["--recipient", fpr])
        changed = git(store, "diff", "--cached", "--quiet", check=False).returncode != 0
        if changed:
            _commit(store, f"agent {login()}: set {name}")
            _after_commit(store)
        return {"name": name, "changed": changed}


def rm_entry(name: str) -> dict:
    """The agent removes its own entry: env/NAME.gpg, committed signed as
    set commits ("agent <login>: rm NAME") and pushed. History is not
    rewritten — the value stays readable to this key in the store's past,
    so a value that may have leaked is rotated at its provider, not removed.
    An absent name changes nothing ("changed": False); an earlier failed
    push is still caught up."""
    store = store_dir()
    with write_lock(store):
        key_of_store(store)
        _check_name(name)
        _require_clean(store)
        _before_write(store)
        rel = os.path.join("env", f"{name}.gpg")
        tracked = git(store, "ls-files", "--error-unmatch", "--", rel, check=False).returncode == 0
        if not tracked:
            # Never committed: an entry no write path leaves (each stages what
            # it writes), removed all the same so that "absent" is true.
            try:
                os.remove(os.path.join(store, rel))
            except FileNotFoundError:
                _push_if_ahead(store)
                return {"name": name, "changed": False}
            return {"name": name, "changed": True}
        git(store, "rm", "-q", "--", rel)
        _commit(store, f"agent {login()}: rm {name}")
        _after_commit(store)
        return {"name": name, "changed": True}


def names(store: str | None = None) -> list[str]:
    d = os.path.join(store or store_dir(), "env")
    try:
        return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".gpg") and NAME_RE.match(f[:-4]))
    except FileNotFoundError:
        return []


def pull(store: str | None = None) -> None:
    """The store brought up to its remote, when it has one; a failure is
    an error (StoreError), never a note: a sync that read a stale copy
    would apply less than the store holds and still say applied."""
    store = store or store_dir()
    with write_lock(store):
        _before_write(store)


def values(store: str | None = None, *, only) -> dict[str, str]:
    """The entries named in `only` that the store holds, decrypted, as
    text. In-process only: nothing here prints or logs a value. A caller
    names what it uses, and there is no "every entry": an agent's own entry
    may hold any bytes, and decrypting every entry made one non-UTF-8 own
    value fail the whole sync, then every provisioning (new-agent
    included), with a byte of it in the error (review of the own-secrets
    PR; #108's Codex P2).
    A value this must read that is not UTF-8 is a StoreError naming the
    entry, never the decoder's message, which quotes the byte."""
    store = store or store_dir()
    key_of_store(store)
    wanted = set(only)
    out = {}
    for name in names(store):
        if name not in wanted:
            continue
        r = gpg("--decrypt", os.path.join(store, "env", f"{name}.gpg"))
        try:
            out[name] = r.stdout.decode()   # exactly as written: many lines, or none
        except UnicodeDecodeError:
            raise StoreError(f"{name}: the value is not UTF-8 text, and this reads it as text") from None
    return out
