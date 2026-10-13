#!/usr/bin/env python3
"""tools/fabric/review_gateway.py — the Codex review's own gateway: the launcher's Codex profile
(agent-fabric ADR-053 rule 3). review_codex.py calls it for `fabric-review --engine codex PR REQUEST
--gateway chatgpt [--codex-home DIR]`; without --gateway the gateway is the environment's and this module
is not used.

    prepare(gateway, environ, signin_home, budget_s) -> Prepared     every refusal, nothing started
    serve(prepared, model, environ)                  -> context manager yielding
        {AGENT_FABRIC_CODEX_BASE_URL: <the gateway's root>, AGENT_FABRIC_CODEX_KEY: <its local key>,
         AGENT_FABRIC_CODEX_ACCOUNT_ID: <the sign-in's account id>}
    which review_codex.py puts in Codex's config.toml and environment for one review; on leaving it the
    gateway is stopped and its scratch removed, on every path (success, failure, timeout, a signal).

THE SIGN-IN (chatgpt). `$CODEX_HOME/auth.json` of the ChatGPT sign-in, by default ~/.codex-chatgpt (the
session's own CODEX_HOME is not read: it may be the account's ~/.codex, which ADR-053 rule 3 keeps from
Codex, and so is refused when --codex-home names it). The file is the reviewing login's, readable by it
alone; auth_mode "chatgpt"; tokens.access_token a JWT; tokens.account_id a UUID. Of the token only `exp`
is decoded (no signature is checked; nothing else is read or logged), and fewer than 30 minutes left,
or less than the review's time budget when that is longer, refuses: refreshing is Codex's own job, in
its own home (`CODEX_HOME=<dir> codex exec` once, or `codex login` again), never this module's.

THE GATEWAY. The fleet's pinned gateway (AGENT_FABRIC_GW_BIN overrides), through the launcher's own
start/stop (tools/fabric/launcher/gateway.py), with plan schema 1: its `--version --json` must list
plan schema 1 and the `openai-responses` protocol, or it is refused by name before anything is written
or started. The plan is gateway_plan.build_responses(): an openai-responses listener on loopback, the
ChatGPT backend (https://chatgpt.com/backend-api/codex), the access token read per attempt from a token
file, one identity route for the model. The token file holds the access token alone, mode 0600, in a
0700 directory made for this review under the login's runtime directory ($XDG_RUNTIME_DIR, else
/run/user/<uid>), beside the plan and the gateway's log; the directory is removed when the review
ends. The local key is in the gateway's descriptor and Codex's environment only. The gateway stops
with this process (PR_SET_PDEATHSIG), so a kill that skips every `finally` does not leave it serving.

What it does not do: refresh a token, read the refresh or id token, send the account id itself (Codex
does, as a static header; the gateway's schema 1 admits no companion but anthropic-beta), or post.
"""
from __future__ import annotations

import contextlib
import importlib.util
import os
import secrets
import shutil
import signal
import sys
import tempfile
import time
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import chatgpt_signin  # noqa: E402
import gateway_plan  # noqa: E402
import gateway_token  # noqa: E402

GATEWAYS = ("chatgpt",)
PROTOCOL = "openai-responses"
PLAN_SCHEMA = 1
DEFAULT_SIGNIN = ".codex-chatgpt"      # below HOME
MIN_TOKEN_LIFE_S = 30 * 60
ENV_BASE_URL, ENV_KEY, ENV_ACCOUNT_ID = (
    "AGENT_FABRIC_CODEX_BASE_URL", "AGENT_FABRIC_CODEX_KEY", "AGENT_FABRIC_CODEX_ACCOUNT_ID")
TOKEN_NAME = "chatgpt.token"


Refused = chatgpt_signin.Refused    # nothing was started, or what was started is stopped; the message never holds a token
jwt_exp = chatgpt_signin.jwt_exp


@dataclass
class SignIn:
    home: str
    account_id: str
    expires_at: int
    access_token: str = field(repr=False)


@dataclass
class Prepared:
    signin: SignIn
    binary: str
    version: dict


# --- the sign-in -------------------------------------------------------------

def signin_home(environ: dict[str, str], flag: str | None) -> str:
    """--codex-home, else HOME/.codex-chatgpt; never the account's ~/.codex."""
    home_dir = environ.get("HOME") or os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(flag)) if flag else os.path.join(home_dir, DEFAULT_SIGNIN)
    if os.path.realpath(path) == os.path.realpath(os.path.join(home_dir, ".codex")):
        raise Refused(f"{path} is the account's ~/.codex, which the Codex engine never reads (agent-fabric ADR-053 "
                      "rule 3); sign in under a CODEX_HOME of its own, ~/.codex-chatgpt by default")
    return path


def read_signin(home: str, *, now: float | None = None, min_life_s: float = MIN_TOKEN_LIFE_S) -> SignIn:
    path = os.path.join(home, "auth.json")
    try:
        access, account, exp = chatgpt_signin.read_signin(home)
    except chatgpt_signin.Missing:
        raise Refused(f"no ChatGPT sign-in at {path}; sign in with `CODEX_HOME={os.path.dirname(path)} codex login`") from None
    except chatgpt_signin.NotSignIn as e:
        raise Refused(f"{e}; sign in with `CODEX_HOME={home} codex login`") from None
    now = time.time() if now is None else now
    left = exp - now
    if left < min_life_s:
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))
        state = "expired" if left <= 0 else f"has {int(left // 60)} minutes left"
        raise Refused(f"the ChatGPT sign-in's access token {state} (until {when}); this review needs "
                      f"{int(min_life_s // 60)} minutes. Run `CODEX_HOME={home} codex exec` once to refresh it, or sign in "
                      f"again (`CODEX_HOME={home} codex login`); nothing was started or posted")
    return SignIn(home, account, exp, access)


# --- the gateway -------------------------------------------------------------

def _launcher():
    """The launcher's gateway module and its Refused, from this checkout's tools/fabric/launcher, loaded by path
    as launch.py loads it (the package's parts import one another as fabric_launcher.*)."""
    if "fabric_launcher" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "fabric_launcher", os.path.join(HERE, "launcher", "__init__.py"),
            submodule_search_locations=[os.path.join(HERE, "launcher")])
        module = importlib.util.module_from_spec(spec)
        sys.modules["fabric_launcher"] = module
        spec.loader.exec_module(module)
    from fabric_launcher import gateway
    from fabric_launcher.base import Refused as LauncherRefused
    return gateway, LauncherRefused


def prepare(gateway: str, environ: dict[str, str], signin_flag: str | None, budget_s: float,
            now: float | None = None) -> Prepared:
    """Everything that can refuse before a file is written or a process started: the sign-in and its token's
    lifetime, then the installed gateway's schemas and protocols."""
    if gateway not in GATEWAYS:
        raise Refused(f"gateway {gateway!r}: the gateways are: {', '.join(GATEWAYS)}")
    signin = read_signin(signin_home(environ, signin_flag), now=now, min_life_s=max(MIN_TOKEN_LIFE_S, budget_s))
    gw, launcher_refused = _launcher()
    try:
        binary = gw.binary_path(environ, FABRIC_ROOT)
        version = gw.check_version(binary, plan_schema=PLAN_SCHEMA, protocol=PROTOCOL)
    except launcher_refused as e:
        raise Refused(str(e)) from None
    return Prepared(signin, binary, version)


def runtime_dir(environ: dict[str, str]) -> str:
    """The login's runtime directory, which the gateway's token-file checks admit (tmpfs, the login's own)."""
    path = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not os.path.isabs(path) or not os.path.isdir(path):
        raise Refused(f"no runtime directory ({path}); the token file is written only there")
    path = os.path.realpath(path)
    try:
        gateway_token.check_directory(path, os.getuid())
    except (gateway_token.TokenFileError, OSError) as e:
        raise Refused(f"the runtime directory cannot hold the token file: {e}") from None
    return path


def _write_token(path: str, token: str) -> None:
    """The access token alone, no newline, in a new file only this login can read (O_EXCL: never an old one)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        os.fchmod(fh.fileno(), 0o600)
        fh.write(token.encode("ascii"))


def _tail(path: str, limit: int = 1500) -> str:
    """The gateway's log, which by its contract names no credential value (plan README, "Validation")."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read().strip()
    except OSError:
        return ""
    return ("…" + text[-limit:]) if len(text) > limit else text


@contextlib.contextmanager
def serve(prep: Prepared, model: str, environ: dict[str, str]):
    """Start the gateway for one review and yield what Codex is given; stop it and remove its scratch on leaving."""
    gw_mod, launcher_refused = _launcher()
    parent = os.path.join(runtime_dir(environ), "agent-fabric")
    os.makedirs(parent, mode=0o700, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="review-codex.", dir=parent)   # 0700, this review's alone
    gw = None
    try:
        token_file = os.path.join(scratch, TOKEN_NAME)
        _write_token(token_file, prep.signin.access_token)
        try:
            plan = gateway_plan.build_responses(model, token_file, session=secrets.token_hex(8))
        except gateway_plan.PlanError as e:
            raise Refused(f"the gateway plan cannot be built: {e}; nothing was started or posted") from None
        plan_path = gateway_plan.write(plan, os.path.join(scratch, "plan.json"))
        log_path = os.path.join(scratch, "gateway.log")
        try:
            gw = gw_mod.start(prep.binary, plan_path, log_path, prep.version,
                              ready_timeout=gw_mod.ready_timeout(environ), plan_schema=PLAN_SCHEMA)
        except launcher_refused as e:
            # The log goes with the scratch, so what it said is said here.
            log = _tail(log_path)
            raise Refused(f"{e}{' The gateway said: ' + log if log else ''} Nothing was posted.") from None
        yield {ENV_BASE_URL: gw.listener, ENV_KEY: gw.key, ENV_ACCOUNT_ID: prep.signin.account_id}
    finally:
        # The token goes first, and no signal may cut this short: stop() waits for the gateway to drain, and a
        # signal raised into that wait once skipped the removal and left the token on disk (review of #224, F1).
        # A signal that arrives meanwhile is delivered when the mask is lifted, after the scratch is gone.
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGTERM, signal.SIGHUP, signal.SIGINT))
        try:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(os.path.join(scratch, TOKEN_NAME))
            if gw is not None:
                gw_mod.stop(gw)
            shutil.rmtree(scratch, ignore_errors=True)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
