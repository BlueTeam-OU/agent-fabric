#!/usr/bin/env python3
"""tools/fabric/chatgpt_signin.py — what the fabric reads of a ChatGPT sign-in: the access token, the account id and
the token's expiry, and nothing else (agent-fabric ADR-053 rule 8). Two files carry them:

  the sign-in      $CODEX_HOME/auth.json, Codex's own (the coordinator's, in ~/.codex-chatgpt): auth_mode
                   "chatgpt", tokens.access_token a JWT, tokens.account_id a UUID. It also holds a refresh token and
                   an id token, which this module never returns, logs or copies: read() parses the document, keeps
                   two strings and an integer, and lets the rest go.
  the synced file  <runtime dir>/agent-fabric/gateway/chatgpt-signin.json on every other login (gateway_token.py,
                   written by `fabric-secrets sync` from the two store entries `fabric-accounts codex-token` put
                   there): {"access_token": …, "account_id": …}, compact JSON, mode 0600, the login's own.

Both are opened without following a link and are refused unless they are regular files of this login that no one else
can read. Of the token only `exp` is decoded: no signature is checked (the backend checks it) and no other claim is
kept. Every refusal is `Refused` with one line that never holds a token; a caller adds what to do about it.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import stat

MAX_AUTH_BYTES = 1 << 20
# An exp is a time a person can read: from 1970 to 2106. A JWT whose exp is anything else is refused here, not left for
# a date formatter (a year past 9999, a negative one) to fail somewhere that would lose more than this sign-in.
EXP_MAX = 2 ** 32
ACCOUNT_ID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
# An Authorization header value: printable ASCII with no space. A JWT is base64url and dots.
HEADER_SAFE = re.compile(r"[!-~]+")


class Refused(Exception):
    """A sign-in that cannot be used; the message says why and never holds a token."""


class Missing(Refused):
    """The file is not there: the one refusal a caller may answer with another source."""


class NotSignIn(Refused):
    """A readable auth.json that is not a ChatGPT sign-in (another auth_mode, no tokens): the caller says how to sign in."""


def read_owned(path: str) -> bytes:
    """The file, opened without following a link, refused unless it is a regular file of this login that no one
    else can read: it holds tokens."""
    try:
        # O_NONBLOCK: a FIFO in the file's place (the login can make one) would otherwise block the open for ever; it opens
        # at once and is refused below as no regular file. A regular file is unaffected.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        raise Missing(f"no sign-in at {path}") from None
    except OSError as e:
        raise Refused(f"{path} cannot be opened ({e.strerror or e.errno}); a link in its place is refused") from None
    st = os.fstat(fd)
    # Before fdopen: a directory opens read-only and fdopen then raises IsADirectoryError, a traceback in place of a refusal.
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise Refused(f"{path} is not a regular file")
    with os.fdopen(fd, "rb") as fh:
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise Refused(f"{path} is readable by another user or not this login's (mode {stat.S_IMODE(st.st_mode):04o}); "
                          "a sign-in is the login's alone: chmod 600 it")
        data = fh.read(MAX_AUTH_BYTES + 1)
    if len(data) > MAX_AUTH_BYTES:
        raise Refused(f"{path} is over {MAX_AUTH_BYTES} bytes; not a sign-in")
    return data


def jwt_exp(token: str) -> int:
    """The `exp` claim of a JWT's payload, read without checking the signature (the token is only forwarded:
    the backend checks it). Nothing else of the payload is kept. ValueError, without the token, otherwise."""
    parts = token.split(".")
    if len(parts) != 3 or not parts[1]:
        raise ValueError("not a JWT (three dot-separated parts)")
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError("its payload is not base64url JSON") from None
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if type(exp) is not int:
        raise ValueError("its payload carries no integer exp")
    if not 0 < exp < EXP_MAX:
        raise ValueError("its exp is not a time between 1970 and 2106")
    return exp


def checked(access: object, account: object, path: str, names: tuple[str, str] = ("access_token", "account_id")) -> tuple[str, str, int]:
    """(access token, account id, exp) of two values read from `path` under the keys `names`, or Refused."""
    if not isinstance(access, str) or not HEADER_SAFE.fullmatch(access):
        raise Refused(f"{path}: {names[0]} is missing or not a header-safe token")
    if not isinstance(account, str) or not ACCOUNT_ID.fullmatch(account):
        raise Refused(f"{path}: {names[1]} is missing or not an account id (a UUID)")
    try:
        exp = jwt_exp(access)
    except ValueError as e:
        raise Refused(f"{path}: {names[0]}: {e}") from None
    return access, account, exp


def read_signin(home: str) -> tuple[str, str, int]:
    """(access token, account id, exp) of $CODEX_HOME/auth.json. Missing when there is no such file; Refused when
    it is not a ChatGPT sign-in. The refresh and id tokens are not returned."""
    path = os.path.join(home, "auth.json")
    try:
        doc = json.loads(read_owned(path))
    except ValueError:
        raise Refused(f"{path} is not JSON") from None
    tokens = doc.get("tokens") if isinstance(doc, dict) else None
    if not isinstance(doc, dict) or doc.get("auth_mode") != "chatgpt" or not isinstance(tokens, dict):
        raise NotSignIn(f"{path} is not a ChatGPT sign-in (auth_mode \"chatgpt\" with tokens)")
    return checked(tokens.get("access_token"), tokens.get("account_id"), path, ("tokens.access_token", "tokens.account_id"))


def synced_text(access: str, account: str) -> str:
    """The synced file's content: compact JSON of the two values, printable ASCII without a space, so it passes
    gateway_token's check for a token."""
    return json.dumps({"access_token": access, "account_id": account}, separators=(",", ":"))


def read_synced(path: str) -> tuple[str, str, int]:
    """(access token, account id, exp) of the synced file; Missing when it is not there."""
    try:
        doc = json.loads(read_owned(path))
    except ValueError:
        raise Refused(f"{path} is not JSON") from None
    if not isinstance(doc, dict):
        raise Refused(f"{path} is not the synced sign-in (a JSON object)")
    return checked(doc.get("access_token"), doc.get("account_id"), path)
