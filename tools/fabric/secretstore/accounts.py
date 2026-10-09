"""tools/fabric/secretstore/accounts.py — Claude account templates and their assignment, and the owner's paper sheet.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import os
import re
import shutil
import sys

from .core import StoreError, login, own_agent_id, home, store_dir, _run, gpg
from .keys import key_of_store
from .entries import _before_write, _push_if_ahead, set_entry, values, names
from .mirrors import resolve, put
from .lock import write_lock


# ── the Claude-account templates (ADR-031), in the coordinator's store ─
TEMPLATE_PREFIX = "CLAUDE_ACCOUNT_"
ASSIGNED_PREFIX = "CLAUDE_ASSIGNED_"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _slug_name(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
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
    vals = values(only=[n for n in names() if n.startswith(TEMPLATE_PREFIX)])
    return [{"account": n[len(TEMPLATE_PREFIX):].lower().replace("_", "-"), "token_sha256_12": _sha12(v) if v else None}
            for n, v in sorted(vals.items()) if n.startswith(TEMPLATE_PREFIX)]


def assign(slug: str, logins: list[str], *, force: bool = False) -> list[dict]:
    """The template's token into each login's store, as its
    CLAUDE_CODE_OAUTH_TOKEN, written by the parent (which cannot read it
    back); the assignment is recorded in the parent's own store, since
    the parent cannot read the child's."""
    own = store_dir()
    with write_lock(own):
        _before_write(own)
        _push_if_ahead(own)   # a record an earlier failed push left behind
        name = _slug_name(slug)
        vals = values(only=[n for n in names() if n == name or n.startswith(ASSIGNED_PREFIX)])
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
