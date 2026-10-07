"""tools/fabric/secretstore/core.py — paths, agent ids, the error types, and the one boundary every git and gpg call crosses.
A part of secret_store.py, which re-exports it; its docstring is the contract."""
from __future__ import annotations

import os
import pwd
import re
import subprocess

from . import lineage as _lineage
# Defined in lineage.py, which the lint loads alone and contributors may not
# change; here so every part keeps importing them from core.
from .lineage import LOGIN_RE, UID_DOMAIN, AGENT_ID_RE, StoreError, born_of  # noqa: F401


# tools/fabric, as it was while this lived in secret_store.py: FABRIC_ROOT is
# the checkout two levels above it.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class NotInLineage(StoreError):
    """No agent with that login or id: the one answer that lets a parent
    mint an id (store-enroll.sh). An unreadable lineage is not this."""


def login() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


# ── the agent id (ADR-039): a UUIDv7 whose timestamp is the birth ─────
REPO_PREFIX = "agent-fabric-secrets-"


def mint_agent_id(born_ms: int) -> str:
    """Minted once and recorded, never recomputed: 74 of its bits are
    random, so the same birth never gives the same id twice — a login
    reused after its agent retired is a new agent (ADR-038 rule 6)."""
    if not 0 <= born_ms < 1 << 48:
        raise StoreError(f"{born_ms} is not a birth in milliseconds since 1970")
    r = int.from_bytes(os.urandom(10), "big")
    v = (born_ms << 80) | (0x7 << 76) | ((r >> 62) & 0xFFF) << 64 | (0b10 << 62) | (r & ((1 << 62) - 1))
    h = f"{v:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def born_ms_of(stamp: str) -> int:
    """A birth as `stat -c %w` prints it ("2026-01-14 21:27:33.247294044
    +0100"), or ISO 8601, or "now"."""
    import datetime
    if stamp == "now":
        return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    m = re.match(r"^(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:\.(\d+))?\s*(Z|[+-]\d\d:?\d\d)?$", stamp.strip())
    if not m:
        raise StoreError(f"{stamp!r} is not a birth time (the home's creation time is unknown here: name one)")
    frac = (m.group(3) or "0")[:6].ljust(6, "0")
    tz = (m.group(4) or "Z").replace("Z", "+00:00")
    tz = tz if ":" in tz else tz[:3] + ":" + tz[3:]
    t = datetime.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}.{frac}{tz}")
    return int(t.timestamp() * 1000)


def own_agent_id(store: str | None = None) -> str | None:
    try:
        with open(os.path.join(store or store_dir(), ".agent-id"), encoding="utf-8") as fh:
            aid = fh.read().strip()
    except FileNotFoundError:
        return None
    if not AGENT_ID_RE.match(aid):
        raise StoreError(f"the store's .agent-id is not an agent id: {aid[:40]!r}")
    return aid


def home() -> str:
    return os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir


def store_dir() -> str:
    return os.environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(home(), ".local", "share", "agent-fabric", "secrets")


def children_dir() -> str:
    return os.path.join(home(), ".local", "share", "agent-fabric", "children")


def keys_dir(fabric: str | None = None) -> str:
    return _lineage.keys_dir(fabric or FABRIC_ROOT)


# What git itself clears when it enters another repository (git rev-parse
# --local-env-vars), and the config the environment injects
# (GIT_CONFIG_KEY_<n>/VALUE_<n> beside GIT_CONFIG_COUNT). Set by a caller —
# a git hook runs with GIT_DIR, a test or a shell can export it — they point
# every `git -C <store>` at another repository: the --local trusted-base read
# returned that repository's base (review of #96). GIT_CONFIG_GLOBAL, _SYSTEM
# and _NOSYSTEM stay: they choose the account's own config files, not a
# repository, and a test isolates its account with them.
_GIT_REPO_ENV = frozenset({
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR"})


def _git_scrubbed(env: dict) -> dict:
    return {k: v for k, v in env.items()
            if k not in _GIT_REPO_ENV and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}


def _run(cmd: list[str], *, stdin: bytes | None = None, cwd: str | None = None,
         env: dict | None = None, check: bool = True, timeout: float | None = None,
         label: str | None = None) -> subprocess.CompletedProcess:
    # What an error names: the caller's label (gpg() and git() pass the
    # operation, which follows their fixed flags), else the command and its
    # first argument.
    what = label or " ".join([os.path.basename(cmd[0])] + cmd[1:2])
    if os.path.basename(cmd[0]) == "git":
        env = _git_scrubbed(os.environ if env is None else env)
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True, cwd=cwd, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StoreError(f"{what}: timed out after {timeout:g} s") from None
    if check and r.returncode != 0:
        raise _failure(what, r)
    return r


def _failure(what: str, r: subprocess.CompletedProcess) -> StoreError:
    # The last line of stderr that is not git's advice ("hint:"), which
    # gpg and git keep free of values; the error, not the suggestion.
    # Where git says what failed ("fatal:", the server's "ERROR:"), that
    # line: its advice can follow it, and a push GitHub refused read
    # "and the repository exists." (python-dev-01's enrolment).
    lines = [l for l in r.stderr.decode(errors="replace").strip().splitlines() if not l.startswith("hint:")]
    said = [l for l in lines if l.startswith(("fatal:", "error:", "ERROR:"))]
    return StoreError(f"{what}: {(said or lines or [f'exit {r.returncode}'])[-1]}")


# gpg's commands, as opposed to its options: what an error names.
GPG_COMMANDS = {"--import", "--export", "--export-secret-keys", "--list-keys", "--list-secret-keys",
                "--check-sigs", "--show-keys", "--encrypt", "--decrypt", "--quick-gen-key", "--quick-add-key",
                "--quick-add-uid", "--quick-sign-key", "--gen-revoke", "--list-packets"}


def gpg(*args: str, stdin: bytes | None = None, homedir: str | None = None, check: bool = True,
        timeout: float | None = None):
    cmd = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", ""]
    if homedir:
        cmd += ["--homedir", homedir]
    op = next((a for a in args if a in GPG_COMMANDS), args[0] if args else "")
    return _run(cmd + list(args), stdin=stdin, check=check, label=f"gpg {op}", timeout=timeout)


def git(store: str, *args: str, check: bool = True):
    return _run(["git", "-C", store, *args], check=check, label=f"git {args[0] if args else ''}")
