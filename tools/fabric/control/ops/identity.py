"""tools/fabric/control/ops/identity.py — who the account is, the session it runs and whether one is present, and the fabric checkout it runs on.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import os
import subprocess
from typing import Any, Callable

from . import util
from gzcoord import gzmsg  # noqa: E402 — util puts tools/fabric on sys.path
from gzcoord.inbox_parts import hold, tokens  # noqa: E402

PGREP_TIMEOUT_S = 5


def identity(home: str | None = None, who: dict | None = None) -> dict:
    """Who this account is, and which Claude account its sessions run on. A
    template's setup-token (CLAUDE_CODE_OAUTH_TOKEN, synced from the
    login's store) outranks the login's own /login, whose ~/.claude.json keeps
    naming its old account — so a switched login is reported by the
    token's fingerprint (`fabric-accounts templates` maps it to an account),
    and its own sign-in separately, never as the account in use."""
    home = os.path.expanduser("~") if home is None else home
    who = gzmsg.whoami() if who is None else who
    cfg = util.read_json(os.path.join(home, ".claude.json"))
    claude = cfg.get("oauthAccount") if isinstance(cfg, dict) else None
    # `claude ? {...} : null` — any truthy value, as the Node read it.
    own = ({"email": claude.get("emailAddress"), "organization": claude.get("organizationName")}
           if isinstance(claude, dict) and claude else None)
    template = tokens.synced_var("CLAUDE_CODE_OAUTH_TOKEN", home)
    out: dict[str, Any] = {
        "agent": who.get("agent"), "host": who.get("host"), "role": who.get("role"),
        "project": who.get("project"), "working_copy": who.get("working_copy"),
        "claude_account": ({"via": "setup-token", "token_sha256_12": util.sha12(template), "email": None, "organization": None}
                           if template else own),
    }
    if template:
        out["own_sign_in"] = own
    out["credentials_present"] = os.path.exists(os.path.join(home, ".claude", ".credentials.json"))
    return out


def fabric(root: str | None = None, run: Callable[..., Any] = subprocess.run) -> dict:
    """The fabric checkout the account runs on: head, branch, how far behind
    origin/main, and whether the tree is clean. A fetch that cannot reach
    origin is said, not hidden. Every git call is bounded at 10 s, so a
    hung fetch costs the section, not the daemon."""
    if root is None:
        root = os.environ.get("AGENT_FABRIC_ROOT")
        if root is None:
            root = os.path.join(os.path.expanduser("~"), "projects", "agent-fabric")

    def git(*a: str) -> str:
        r = run(["git", "-C", root, *a], capture_output=True, text=True, errors="replace", timeout=10, check=True,
                stdin=subprocess.DEVNULL)
        return r.stdout.strip()

    out: dict[str, Any] = {"root": root}
    failed = (subprocess.SubprocessError, OSError)
    try:
        out["head"] = git("rev-parse", "--short", "HEAD")
    except failed:
        return {**out, "status": "not-a-checkout"}
    try:
        out["branch"] = git("rev-parse", "--abbrev-ref", "HEAD")
    except failed:
        out["branch"] = None
    try:
        out["dirty"] = len(git("status", "--porcelain")) > 0
    except failed:
        out["dirty"] = None
    try:
        git("fetch", "-q", "origin", "main")
        out["fetch"] = "ok"
    except failed:
        out["fetch"] = "failed"
    try:
        out["behind"] = int(git("rev-list", "--count", "HEAD..origin/main"))
    except (*failed, ValueError):
        out["behind"] = None
    return {"status": "ok", **out}


def session(uid: int | None = None, run: Callable[..., Any] = subprocess.run) -> dict:
    """Whether a harness runs as this account, and whether it is planning."""
    uid = os.getuid() if uid is None else uid
    try:
        r = run(["pgrep", "-u", str(uid), "-x", "claude"], capture_output=True, text=True, timeout=PGREP_TIMEOUT_S,
                stdin=subprocess.DEVNULL)
        # pgrep exits 1 when nothing matches
        n = len([x for x in r.stdout.strip().split("\n") if x]) if r.returncode == 0 else 0
    except (subprocess.SubprocessError, OSError):
        n = 0
    return {"claude_processes": n, "planning": hold.hold_status()["held"]}


def _pgrep_failure(e: BaseException, uid: int) -> str:
    """The message the Node op put in its reply, so the reply's text is the same."""
    if isinstance(e, subprocess.TimeoutExpired):
        return "spawnSync pgrep ETIMEDOUT"
    if isinstance(e, subprocess.CalledProcessError):
        return f"Command failed: pgrep -u {uid} -x claude"
    if isinstance(e, FileNotFoundError):
        return "spawnSync pgrep ENOENT"
    return str(e)


def presence(uid: int | None = None, run: Callable[..., Any] = subprocess.run, proc: str = "/proc",
             self_pid: int | None = None, who: dict | None = None, binding: dict | None = None,
             hold_status: Callable[[], dict] = hold.hold_status) -> dict:
    """Presence: whether this account has a session, from the process table,
    so a crash or a launch that never reached the harness is never
    "present" — the two cases the retired HELLO/GOODBYE pair got wrong on
    2026-09-25.
    The daemon's own children (the observer's /usage runs) are not a
    session. The role is derived exactly as the inbox's delivery derives it
    (identity() in gzcoord, the binding's role, else the slug the login
    carries), so a TO-ROLE the relay would deliver is never refused for a
    holder with no role recorded (review of #38). The project is the
    binding's: where the last session here worked."""
    uid = os.getuid() if uid is None else uid
    self_pid = os.getpid() if self_pid is None else self_pid
    pids: list[int] = []
    try:
        r = run(["pgrep", "-u", str(uid), "-x", "claude"], capture_output=True, text=True, timeout=PGREP_TIMEOUT_S,
                check=True, stdin=subprocess.DEVNULL)
        pids = [int(x) for x in str(r.stdout).strip().split("\n") if x]
    except subprocess.CalledProcessError as e:
        if e.returncode != 1:
            return {"status": "failed", "error": f"pgrep: {_pgrep_failure(e, uid).split(chr(10))[0][:120]}"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "error": f"pgrep: {_pgrep_failure(e, uid).split(chr(10))[0][:120]}"}

    def stat(p: int) -> list[str] | None:
        try:
            with open(os.path.join(proc, str(p), "stat"), encoding="utf-8", errors="replace") as fh:
                s = fh.read()
        except OSError:
            return None
        return s[s.rfind(")") + 2:].split(" ")

    btime: int | None = None
    try:
        with open(os.path.join(proc, "stat"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("btime "):
                    btime = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        btime = None
    live = [(p, f) for p in pids if (f := stat(p)) and float(f[1]) != self_pid]
    # field 22 of stat, starttime, in clock ticks since boot (USER_HZ, 100 on Linux)
    starts = sorted(util.iso_ms((btime + float(f[19]) / 100) * 1000) for _, f in live if btime is not None)
    me = gzmsg.whoami() if who is None else who
    b = binding if binding is not None else util.read_json(me.get("binding") or "")
    if not isinstance(b, dict):
        b = {}
    role = None
    try:
        tp = gzmsg.find_taxonomy()
        role = tokens.identity(me, gzmsg.load_taxonomy(tp) if tp else None).get("slug")
    except Exception:  # noqa: BLE001 — no catalogue: no role
        role = None
    # Planning: the account's inbox is held until the plan is approved
    # (docs/adr/ADR-022-the-session-lifecycle.md), so a message sent now is read
    # then, and a sender should not wait on an answer before.
    planning = False
    try:
        planning = bool(live) and hold_status().get("held") is True
    except Exception:  # noqa: BLE001 — no hold directory: not planning
        planning = False
    return {"status": "ok", "online": bool(live), "sessions": len(live), "since": starts[0] if starts else None,
            "role": role, "project": b.get("project"), "planning": planning}
