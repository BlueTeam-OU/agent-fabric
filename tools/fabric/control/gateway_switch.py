"""tools/fabric/control/gateway_switch.py — what `secrets-sync` proves about a session on the gateway
(gateway-switch s8).

A session launched with --provider gateway holds no Claude token: the gateway holds the account's credential as a
token file it re-reads on every upstream attempt (the gateway's control-plane contract §10), so replacing the file is
the whole switch — no restart, no new plan generation. `fabric-secrets sync` has already done that when this runs
(gateway_token.write: a new file renamed into place, a new inode).

What the controller can say about it, and what it cannot:
  * The gateway never reports an account. It logs a credential change by GENERATION, the opened file's device, inode
    and modification time, "never by value or digest", and "gateway logs carry no account label" (its ADR-012 rule
    17). So the join is the controller's: when it replaces the file it records generation -> the token's
    fingerprint (the setup-token's sha256, 12 hex digits, which `fabric-accounts templates` maps to an account) in
    <state>/gateway-generations.json.
  * The gateway has taken the new file up when its log (the launcher keeps the gateway's stderr in
    <state>/gateway.log) carries a `credential.replaced` line with that generation. It writes it on the first
    attempt that uses the file, so before a request has gone through the answer is "not yet", never "yes": a switch
    the gateway has not confirmed is reported, not assumed.
  * Nothing here sends a request: the local key is the session's own, and a probe on its behalf is a decision for the
    owner, not for a daemon.

The join file is a list, newest last, of {at, fingerprint, generation, via}; a generation already the newest is not
recorded twice; the list keeps the last KEEP.
"""
from __future__ import annotations

import json
import os
import re
import stat
from typing import Any

JOIN = "gateway-generations.json"
LOG = "gateway.log"
KEEP = 50
# The tail of the log read. A credential.replaced line is written once per generation, but a busy gateway logs
# much after it, so the window is generous; a line pushed out of it reads as "not yet", which is why it is large.
LOG_TAIL_BYTES = 64_000_000
TOKEN_MAX = 65_536
ANSI = re.compile(r"\x1b\[[0-9;]*m")
FIELDS = ("device", "inode", "mtime_sec", "mtime_nsec")


def open_token(path: str):
    """(generation, the file's text) from ONE open, so the identity and the content are the same file even when a
    sync replaces it meanwhile; a symlink is refused (O_NOFOLLOW), as the gateway refuses it. (None, None) where
    the file is absent, not a regular file, or unreadable. O_NONBLOCK: a FIFO there must be refused, not waited on."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None, None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, None
        with os.fdopen(fd, "rb", closefd=False) as fh:
            text = fh.read(TOKEN_MAX).decode("utf-8", "replace")
    except OSError:
        return None, None
    finally:
        os.close(fd)
    return {"device": st.st_dev, "inode": st.st_ino, "mtime_sec": st.st_mtime_ns // 1_000_000_000,
            "mtime_nsec": st.st_mtime_ns % 1_000_000_000}, text


def generation_of(path: str) -> dict[str, int] | None:
    return open_token(path)[0]


def read_join(state_dir: str) -> list[dict]:
    try:
        with open(os.path.join(state_dir, JOIN), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return []
    return [e for e in doc if isinstance(e, dict)] if isinstance(doc, list) else []


def record(state_dir: str, generation: dict[str, int], fingerprint: str, at: str, via: str = "secrets-sync") -> bool:
    """Append generation -> fingerprint, unless it is already the newest entry. Atomic. False when nothing was
    written (already there, or the directory cannot be written: the join is evidence, never a reason to fail)."""
    entries = read_join(state_dir)
    if entries and entries[-1].get("generation") == generation and entries[-1].get("fingerprint") == fingerprint:
        return False
    entries.append({"at": at, "fingerprint": fingerprint, "generation": generation, "via": via})
    path = os.path.join(state_dir, JOIN)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
            json.dump(entries[-KEEP:], fh)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass   # never created, or gone
        return False
    return True


def latest(state_dir: str) -> dict | None:
    entries = read_join(state_dir)
    return entries[-1] if entries else None


def confirmed(log_path: str, generation: dict[str, int]) -> bool | None:
    """True when the gateway's log carries a `credential.replaced` line for this generation; False when the log
    is readable and does not (no request has used the file yet); None when the log cannot be read."""
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - LOG_TAIL_BYTES))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in text.splitlines():
        if "credential.replaced" not in line:
            continue
        seen = {k: int(v) for k, v in re.findall(r"(?<![\w.])(device|inode|mtime_sec|mtime_nsec)=(\d+)", ANSI.sub("", line))}
        if all(seen.get(k) == generation[k] for k in FIELDS):
            return True
    return False


def prove(state_dir: str, token_file: str, token_sha12: str | None, at: str) -> dict[str, Any]:
    """After a sync, for a session on the gateway: the answer for the reply. {"session": the words,
    "detail": the machine form}. The file must hold the synced token (its fingerprint is the one recorded);
    one that does not, or is absent, is said and nothing is joined."""
    from control.ops import util
    gen, text = open_token(token_file)
    if token_sha12 is None:
        words = ("running (gateway): the synced record holds no token, so the gateway's file was taken away; its next "
                 "request is refused" if gen is None else
                 "running (gateway): the synced record holds no token, but the gateway's file still holds one; "
                 "remove it, or the gateway keeps serving the old account")
        return {"session": words,
                "detail": {"generation": gen, "fingerprint": None, "confirmed": None}}
    if gen is None:
        return {"session": "running (gateway): the token file is absent after the sync; the gateway cannot serve the new account",
                "detail": {"generation": None, "fingerprint": token_sha12, "confirmed": None}}
    held = util.sha12(text.rstrip("\n"))
    if held != token_sha12:
        return {"session": "running (gateway): the token file does not hold the synced token; the gateway is not on the new account",
                "detail": {"generation": gen, "fingerprint": token_sha12, "confirmed": None, "file_fingerprint": held}}
    record(state_dir, gen, token_sha12, at)
    ok = confirmed(os.path.join(state_dir, LOG), gen)
    if ok is True:
        words = f"running (gateway): on the new account (setup-token {token_sha12}), confirmed by the gateway's own log"
    elif ok is False:
        words = (f"running (gateway): token file replaced (setup-token {token_sha12}); not yet confirmed — "
                 "the gateway takes it at its next request")
    else:
        words = f"running (gateway): token file replaced (setup-token {token_sha12}); the gateway's log cannot be read, so unconfirmed"
    return {"session": words, "detail": {"generation": gen, "fingerprint": token_sha12, "confirmed": ok}}
