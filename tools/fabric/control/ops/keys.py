"""tools/fabric/control/ops/keys.py — which keys the account holds, whether its stores took only verified commits, and whether it can sign.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Callable

from . import util
from gzcoord import jsvalues as js  # noqa: E402 — util puts tools/fabric on sys.path
from gzcoord.inbox_parts.tokens import synced_var  # noqa: E402

KEY_NAMES = ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN",
             "SERPAPI_API_KEY", "BRAVE_SEARCH_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"]


def keys(home: str | None = None, names: list[str] = KEY_NAMES) -> list[dict]:
    """Which keys the account holds, by name and fingerprint; never a value."""
    home = os.path.expanduser("~") if home is None else home
    out = []
    for name in names:
        v = synced_var(name, home)
        out.append({"name": name, "present": True, "sha256_12": util.sha12(v)} if v else {"name": name, "present": False})
    return out


# Whether this account's stores took only verified commits (ADR-042 rule
# 5): its own store and each child's mirror. A refusal is a security event,
# said until the store is repaired; secret_store.py keeps the last one
# beside the store, and nothing here reads an entry. The row's state:
# verified, refused, no store, no base (it verifies nothing, so takes
# nothing in), or unreadable — never "verified" for a store that is not
# there or has no base (review of ADR-042, F4). A mirror's refusal is the
# parent's to repair, named by the child's agent id (F3).
STORE_ROW = "store commits verified"

REFUSAL_FILE = "agent-fabric-refusal.json"

AGENT_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def _read_text(file: str) -> str:
    # The Node read decoded with replacement; a refusal file with a bad byte is still a refusal.
    with open(file, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _read_refusal(store: str, kept: str | None = None) -> dict | None:
    """None: no refusal. {"unreadable": True}, or {"refused": {...}}.
    kept: where a child's mirror's refusal is kept once a refused rebuild
    removed the mirror — beside it, `<id>.refusal.json` (secret_store.py)."""
    try:
        r = util.loads(_read_text(os.path.join(store, ".git", REFUSAL_FILE)))
    except FileNotFoundError:
        if not kept:
            return None
        try:
            r = util.loads(_read_text(kept))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {"unreadable": True}
    except (OSError, ValueError):
        return {"unreadable": True}
    return {"refused": {"commit": js.string(js.coalesce(js.get(r, "commit"), "?"))[:12],
                        "at": None if js.nullish(js.get(r, "at")) else r["at"],
                        "reason": js.string(js.coalesce(js.get(r, "reason"), "?"))[:300]}}


_SECTION = re.compile(r"\s*\[([^\]]*)\]")
_TRUSTEDBASE = re.compile(r"\s*trustedbase\s*=\s*(.*?)\s*", re.I)
_SHA1 = re.compile(r"[0-9a-f]{40}")


def _has_base(store: str) -> bool | None:
    """The trusted base is agent-fabric.trustedbase in the store's own
    .git/config, which secret_store.py writes through `git config`: read as a
    file, so the keys probe runs no git. True, False, or None (unreadable).
    As the verifier reads it (secret_store.trusted_base): the key's name in
    any case, its last value, and that value 40 lowercase hex — an uppercase
    one, or a good line before a bad one, read "verified" here while every
    verified operation refused the store."""
    try:
        text = _read_text(os.path.join(store, ".git", "config"))
    except OSError:
        return None
    in_section = False
    base = False
    for line in text.split("\n"):
        head = _SECTION.match(line)
        if head:
            in_section = head.group(1).strip().lower() == "agent-fabric"
            continue
        kv = _TRUSTEDBASE.fullmatch(line)
        if in_section and kv:
            base = _SHA1.fullmatch(kv.group(1)) is not None
    return base


def store_refusal(home: str | None = None, store: str | None = None, children: str | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    if store is None:
        store = os.environ.get("AGENT_FABRIC_SECRET_STORE")
        if store is None:
            store = os.path.join(home, ".local", "share", "agent-fabric", "secrets")
    if children is None:
        children = os.path.join(home, ".local", "share", "agent-fabric", "children")
    kids: list[str] = []
    gone: list[str] = []
    try:
        names = os.listdir(children)
        kids = [n for n in names if AGENT_ID_RE.fullmatch(n)]
        gone = [n[:-len(".refusal.json")] for n in names if n.endswith(".refusal.json")]
        gone = [aid for aid in gone if AGENT_ID_RE.fullmatch(aid) and aid not in kids]
    except OSError:
        pass   # no mirrors
    mirrors: list[dict] = []
    # A mirror with no base refuses every verified operation on it, so it is
    # as unclean as a refusal (review of #94): said, as the own store's is. A
    # mirror a refused rebuild removed is said by its kept refusal alone: no
    # base to read where there is no mirror (review of #96).
    for aid in sorted([*kids, *gone]):
        mirror = os.path.join(children, aid)
        r = _read_refusal(mirror, os.path.join(children, f"{aid}.refusal.json"))
        base = True if aid in gone else _has_base(mirror)
        if r:
            mirrors.append({"agent_id": aid, **r.get("refused", {"unreadable": True})})
        elif base is not True:
            mirrors.append({"agent_id": aid, "state": "unreadable" if base is None else "no base"})
    has_store = os.path.exists(os.path.join(store, ".git"))
    own = _read_refusal(store) if has_store else None
    base = _has_base(store) if has_store else None
    if not has_store:
        state = "no store"
    elif own and own.get("unreadable"):
        state = "unreadable"
    elif own and own.get("refused"):
        state = "refused"
    elif base is None:
        state = "unreadable"
    else:
        state = "verified" if base else "no base"
    row: dict[str, Any] = {"name": STORE_ROW, "present": state == "verified" and not mirrors, "state": state}
    if own and own.get("refused"):
        row["refused"] = own["refused"]
    if mirrors:
        row["mirrors"] = mirrors
    return row


# Whether the secret of the key git signs with is in this account's
# keyring and can sign: present or not, never the key. A secret-key COUNT
# is no answer, since every account holds its own store key (ADR-038):
# rust-ui-dev-01 held one and could not sign (2026-10-03). A stub (`#` in
# the colon listing's 15th field, an offline primary) cannot sign either,
# so presence is a sec or ssb line with signing capability and no stub
# mark. git config exits 1 when unset, gpg non-zero when the key is
# unknown: both are absent.
SIGNING_ROW = "signing key secret"


def signing_secret(run: Callable[..., Any] = subprocess.run) -> dict:
    opts: dict[str, Any] = {"capture_output": True, "text": True, "errors": "replace", "timeout": 5, "check": True,
                            "stdin": subprocess.DEVNULL}
    try:
        k = run(["git", "config", "--global", "user.signingkey"], **opts).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        k = ""
    if not k:
        return {"name": SIGNING_ROW, "present": False}
    try:
        listing = run(["gpg", "--list-secret-keys", "--with-colons", "--", k], **opts).stdout
    except (subprocess.SubprocessError, OSError):
        return {"name": SIGNING_ROW, "present": False}
    signs = False
    for line in listing.split("\n"):
        f = line.split(":")
        if f[0] in ("sec", "ssb") and "s" in (f[11] if len(f) > 11 else "") and (f[14] if len(f) > 14 else None) != "#":
            signs = True
    return {"name": SIGNING_ROW, "present": signs}
