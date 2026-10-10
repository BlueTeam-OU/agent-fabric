"""tools/fabric/launcher/gateway.py — the gateway path: `--provider gateway`.
A part of tools/fabric/launch.py, whose docstring is the contract.

The harness talks to the gateway on a loopback port, holding only a
gateway-local key; the gateway holds the upstream credential (the account's
token file, re-read on every attempt) and routes by the plan the generator
(tools/fabric/gateway_plan.py) writes. So `fabric-accounts assign` takes effect
on the next request, with no session restart. The contract with the gateway is
its control-plane-contract.md §11, §12, §14, §15 and the plan-v0 README
(runtime_contract 1).

THE ORDER, each step refusing before the next: the installed gateway's
`--version --json` names a runtime_contract and plan schemas this launcher
supports; the plan is written and its bytes digested; `serve --plan P
--local-key-fd K --ready-fd R --control-fd C` is started with the key on K
(written before the start, so no read can wait on it), a pipe for R and the
gateway's end of a socket pair for C (the launcher keeps the other end: holding
it is the authority to activate a later plan; this launch never does); the
READY record is read, and must name a contract and plan schema supported, a
loopback listener and the digest of the plan written; only then does the harness
start, with ANTHROPIC_BASE_URL the listener, ANTHROPIC_API_KEY the local key, and
every upstream credential removed from its environment (control-plane-contract.md
§11, "Controller obligation": a harness that bypasses its base URL has nothing to
present upstream). The gateway stops when the session ends.

PROCESS LIFETIME (§15): the gateway is a child in a session of its own, so the
terminal's Ctrl-C, which the harness takes as "interrupt this turn", does not end
it. It dies with this launcher: PR_SET_PDEATHSIG (SIGTERM) set in the child before
exec, with a check, in the same step, that the parent is still the process this
launcher recorded before the fork — closing the one window the gateway cannot (a
launcher that dies after the fork and before the gateway's first instruction).
The signal is tied to the thread that forks, so the fork is made from the main
thread, which lives as long as the launcher.

The local key is 256 random bits, in the gateway's descriptor and the harness's
environment and nowhere else: not argv, not a file, not the state record.
"""
from __future__ import annotations

import ctypes
import datetime
import hashlib
import json
import os
import re
import secrets
import select
import signal
import socket
import subprocess
import time
from dataclasses import dataclass

from fabric_launcher.base import BROKER_ENV, _load, die, say

# The runtime_contract values and plan schema versions this launcher speaks
# (the gateway repository's architecture/contracts/plan-v0/README.md). A contract
# the gateway reports and this tuple lacks is refused before anything starts.
SUPPORTED_RUNTIME_CONTRACTS = (1,)
PLAN_SCHEMA = 0
VERSION_TIMEOUT_S = 30
READY_TIMEOUT_S = 30
STOP_WAIT_S = 5
MAX_PLAN_BYTES = 1 << 20
LISTENER = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
PR_SET_PDEATHSIG = 1

# The credentials a harness would present upstream, were it to bypass its base
# URL; none may reach it. ANTHROPIC_API_KEY is replaced by the local key below.
UPSTREAM_CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")

# What each exit code of runtime_contract 1 means (plan-v0 README).
EXIT_MEANING = {2: "a usage error", 3: "the plan was refused (see the gateway's log)",
                4: "a credential source or the local key was unavailable (the account's token file?)",
                5: "the listener could not be bound"}


@dataclass
class Gateway:
    proc: subprocess.Popen
    listener: str
    plan_digest: str
    version: str
    runtime_contract: int
    key: str
    control: socket.socket
    started_at: str

    @property
    def pid(self) -> int:
        return self.proc.pid


def pinned_name(fabric_root: str) -> str:
    """The installed executable's name, from the fleet's pin (runtime/gateway.json:
    the basename of a release's tarball member, which the install action renames
    into ~/.local/bin). The name is the pin's, so no project name is in this file."""
    path = os.path.join(fabric_root, "runtime", "gateway.json")
    try:
        with open(path, encoding="utf-8") as fh:
            releases = json.load(fh)["releases"]
        for arches in releases.values():
            for entry in arches.values():
                name = os.path.basename(entry["member"])
                if name:
                    return name
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    die(f"{path} names no gateway executable (a release's member). Nothing started.")


def binary_path(env: dict, fabric_root: str) -> str:
    """AGENT_FABRIC_GW_BIN; else the pinned executable in ~/.local/bin, where the
    install action puts it; else on PATH."""
    named = env.get("AGENT_FABRIC_GW_BIN", "")
    if named:
        return named
    name = pinned_name(fabric_root)
    found = _which(name, os.path.join(env.get("HOME", ""), ".local", "bin") + os.pathsep + env.get("PATH", ""))
    if not found:
        die(f"{name} is not installed (not in ~/.local/bin or on PATH, and AGENT_FABRIC_GW_BIN is not set). Nothing started.")
    return found


def _which(name: str, path: str) -> str | None:
    for d in path.split(os.pathsep):
        cand = os.path.join(d or ".", name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def check_version(binary: str, timeout: float = VERSION_TIMEOUT_S) -> dict:
    """`<binary> --version --json`, refused unless its runtime_contract and plan
    schemas are ones this launcher supports. Nothing is started before this."""
    try:
        r = subprocess.run([binary, "--version", "--json"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"{binary} --version --json did not answer within {timeout:g} s. Nothing started.")
    except OSError as exc:
        die(f"{binary} cannot run ({exc.strerror or exc}). Nothing started.")
    if r.returncode != 0:
        die(f"{binary} --version --json exited {r.returncode}. Nothing started.")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    if (not isinstance(doc, dict) or not isinstance(doc.get("gateway_version"), str)
            or type(doc.get("runtime_contract")) is not int or not isinstance(doc.get("plan_schemas"), list)):
        die(f"{binary} --version --json did not answer {{gateway_version, runtime_contract, plan_schemas}}. Nothing started.")
    if doc["runtime_contract"] not in SUPPORTED_RUNTIME_CONTRACTS:
        die(f"the installed gateway {doc['gateway_version']} speaks runtime contract {doc['runtime_contract']}; "
            f"this launcher supports {', '.join(map(str, SUPPORTED_RUNTIME_CONTRACTS))}. Nothing started.")
    if not any(type(s) is int and s == PLAN_SCHEMA for s in doc["plan_schemas"]):
        die(f"the installed gateway {doc['gateway_version']} accepts plan schemas {doc['plan_schemas']}, not {PLAN_SCHEMA}, "
            "the one the plan generator writes. Nothing started.")
    return doc


def plan_digest(path: str) -> str:
    """sha256 of the plan file's exact bytes, as the gateway digests them."""
    try:
        if os.path.getsize(path) > MAX_PLAN_BYTES:
            die(f"the plan {path} is over {MAX_PLAN_BYTES} bytes. Nothing started.")
        with open(path, "rb") as fh:
            return "sha256:" + hashlib.sha256(fh.read()).hexdigest()
    except OSError as exc:
        die(f"the plan {path} cannot be read ({exc.strerror or exc}). Nothing started.")


def _parent_guard(launcher_pid: int):
    libc = ctypes.CDLL(None, use_errno=True)

    def child() -> None:
        # The signal survives execve; the check closes the window before it.
        if libc.prctl(PR_SET_PDEATHSIG, int(signal.SIGTERM), 0, 0, 0) != 0 or os.getppid() != launcher_pid:
            os._exit(127)
    return child


def _read_ready(fd: int, proc: subprocess.Popen, timeout: float) -> bytes:
    """The READY line; b"" if the channel closed without one."""
    deadline = time.monotonic() + timeout
    buf = b""
    while b"\n" not in buf:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError
        ready, _, _ = select.select([fd], [], [], left)
        if not ready:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            return buf
        buf += chunk
        if len(buf) > 65536:
            return buf
    return buf


def start(binary: str, plan_path: str, log_path: str, version: dict, *, ready_timeout: float = READY_TIMEOUT_S,
          launcher_pid: int | None = None) -> Gateway:
    """Start the gateway on `plan_path` and wait for READY; the harness starts
    only after this returns. A start that fails stops what it started."""
    digest = plan_digest(plan_path)
    key = secrets.token_hex(32)
    launcher_pid = os.getpid() if launcher_pid is None else launcher_pid
    key_r, key_w = os.pipe()
    ready_r, ready_w = os.pipe()
    mine, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    proc = None
    try:
        # Written before the start: the pipe holds it, so the gateway's read cannot wait on us.
        os.write(key_w, key.encode("ascii"))
        os.close(key_w)
        key_w = -1
        argv = [binary, "serve", "--plan", plan_path, "--local-key-fd", str(key_r), "--ready-fd", str(ready_w),
                "--control-fd", str(theirs.fileno())]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log_fd,
                                pass_fds=(key_r, ready_w, theirs.fileno()), start_new_session=True,
                                preexec_fn=_parent_guard(launcher_pid))
    except OSError as exc:
        _close(key_w, key_r, ready_r, ready_w, log_fd)
        mine.close()
        theirs.close()
        die(f"{binary} cannot start ({exc.strerror or exc}). Nothing started.")
    # The child has its copies; ours must close, or READY's channel never reaches end of file.
    _close(key_r, ready_w, log_fd)
    theirs.close()
    try:
        try:
            line = _read_ready(ready_r, proc, ready_timeout)
        except TimeoutError:
            raise _Refuse(f"the gateway did not report READY within {ready_timeout:g} s (its log: {log_path})") from None
        if not line.endswith(b"\n"):
            code = _reap(proc)
            what = ("closed its READY channel and kept running" if code is None
                    else EXIT_MEANING.get(code, f"exit {code}"))
            raise _Refuse(f"the gateway stopped before READY ({what}; its log: {log_path})")
        ready = _parse_ready(line, digest)
    except _Refuse as why:
        mine.close()
        _kill(proc)
        os.close(ready_r)
        die(f"{why}. Nothing started.")
    os.close(ready_r)
    return Gateway(proc, ready["listener"], ready["plan_digest"], str(version["gateway_version"]), ready["runtime_contract"],
                   key, mine, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


class _Refuse(Exception):
    pass


def _parse_ready(line: bytes, digest: str) -> dict:
    try:
        doc = json.loads(line.decode("utf-8"))
    except ValueError:
        doc = None
    if not isinstance(doc, dict) or doc.get("event") != "ready":
        raise _Refuse("the gateway's first line was not a READY record")
    if type(doc.get("runtime_contract")) is not int or doc["runtime_contract"] not in SUPPORTED_RUNTIME_CONTRACTS:
        raise _Refuse(f"READY names runtime contract {doc.get('runtime_contract')!r}, which this launcher does not support")
    if type(doc.get("plan_schema")) is not int or doc["plan_schema"] != PLAN_SCHEMA:
        raise _Refuse(f"READY names plan schema {doc.get('plan_schema')!r}, not {PLAN_SCHEMA}")
    listener = doc.get("listener")
    if not isinstance(listener, str) or not LISTENER.fullmatch(listener) or int(LISTENER.fullmatch(listener).group(1)) > 65535:
        raise _Refuse(f"READY names a listener that is not loopback http: {listener!r}")
    if not isinstance(doc.get("plan_digest"), str) or not DIGEST.fullmatch(doc["plan_digest"]):
        raise _Refuse("READY carries no plan digest")
    if doc["plan_digest"] != digest:
        raise _Refuse(f"READY reports plan {doc['plan_digest']}, not the {digest} that was written")
    return doc


def _close(*fds: int) -> None:
    for fd in fds:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def _reap(proc: subprocess.Popen, wait: float = 2.0) -> int | None:
    try:
        return proc.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        return None


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def stop(gw: Gateway) -> None:
    """End the gateway when the session ends: SIGTERM (a clean exit), then SIGKILL
    after STOP_WAIT_S. The control socket closes first; end of file ends
    activations, not the gateway."""
    try:
        gw.control.close()
    except OSError:
        pass
    _kill(gw.proc)


def harness_env(gw: Gateway, env: dict) -> None:
    """The harness's environment: the loopback listener, the local key, and no
    upstream credential, nor anything the broker path sets."""
    for name in (*UPSTREAM_CREDENTIALS, *BROKER_ENV):
        env.pop(name, None)
    env["ANTHROPIC_BASE_URL"] = gw.listener
    env["ANTHROPIC_API_KEY"] = gw.key


APPROVED_KEEP = 100


def approve_key(path: str, key: str) -> None:
    """The interactive harness asks "Do you want to use this API key?" (default No)
    about any ANTHROPIC_API_KEY it has not been told it may use, and a gateway-local
    key is new on every launch. It records an answer as the key's last 20 characters in
    ~/.claude.json's customApiKeyResponses.approved (read back on 2.1.285: with the
    entry there, the session opens with no question). The first-run wizard is marked
    done as well: a login on the gateway has no /login to onboard. Atomic, mode 0600;
    the list keeps the latest APPROVED_KEEP entries, since each launch adds one."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        doc = {}
    except (OSError, ValueError) as exc:
        say(f"launch: {path}: {exc}")
        raise _Refuse(f"could not approve the gateway-local key in {path}") from None
    if not isinstance(doc, dict):
        say(f"launch: {path} is not a JSON object")
        raise _Refuse(f"could not approve the gateway-local key in {path}")
    responses = doc.get("customApiKeyResponses")
    if not isinstance(responses, dict):
        responses = {}
    approved = [a for a in responses.get("approved", []) if isinstance(a, str)] if isinstance(responses.get("approved"), list) else []
    rejected = [a for a in responses.get("rejected", []) if isinstance(a, str)] if isinstance(responses.get("rejected"), list) else []
    tail = key[-20:]
    approved = [a for a in approved if a != tail][-(APPROVED_KEEP - 1):] + [tail]
    doc["customApiKeyResponses"] = {**responses, "approved": approved, "rejected": [r for r in rejected if r != tail]}
    doc["hasCompletedOnboarding"] = True
    tmp = f"{path}.fabric-tmp-{os.getpid()}"
    try:
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        say(f"launch: {path}: {exc}")
        raise _Refuse(f"could not approve the gateway-local key in {path}") from None


def record_state(state_dir: str, gw: Gateway) -> None:
    """§16: pid, binary version, listener, plan digest, started_at, beside the
    binding. No key. Atomic; a failure is said, not fatal."""
    path = os.path.join(state_dir, "gateway.json")
    try:
        os.makedirs(state_dir, exist_ok=True)
        tmp = f"{path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"pid": gw.pid, "gateway_version": gw.version, "runtime_contract": gw.runtime_contract,
                       "listener": gw.listener, "plan_digest": gw.plan_digest, "started_at": gw.started_at}, fh)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        say(f"launch: could not record the gateway in {path}: {exc}")


def forget_state(state_dir: str, pid: int) -> None:
    """Remove the record, but only if it is this gateway's: a second launch of
    the login has written its own over it, and that one is still running."""
    path = os.path.join(state_dir, "gateway.json")
    try:
        with open(path, encoding="utf-8") as fh:
            if json.load(fh).get("pid") != pid:
                return
        os.unlink(path)
    except (OSError, ValueError, AttributeError):
        pass


def clear_harness_env(gw: Gateway, env: dict) -> None:
    """After the session: the listener and key this launcher set are gone from its
    own environment, so a re-exec or the next gateway's does not inherit them."""
    if env.get("ANTHROPIC_BASE_URL") == gw.listener:
        env.pop("ANTHROPIC_BASE_URL", None)
    if env.get("ANTHROPIC_API_KEY") == gw.key:
        env.pop("ANTHROPIC_API_KEY", None)


def ready_timeout(env: dict) -> float:
    """AGENT_FABRIC_GW_READY_TIMEOUT_S, for a test or a slow host; a value
    that is not a positive number is said and the default used."""
    raw = env.get("AGENT_FABRIC_GW_READY_TIMEOUT_S", "")
    if not raw:
        return READY_TIMEOUT_S
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    say(f"launch: AGENT_FABRIC_GW_READY_TIMEOUT_S is not a positive number ('{raw}'); using {READY_TIMEOUT_S:g}")
    return READY_TIMEOUT_S


def launch_gateway(env: dict, fabric_root: str, agent: str, role: str, state_dir: str, session_model: str) -> Gateway:
    """Everything between "the launch is decided" and "the harness may start":
    the installed gateway checked, the plan built by tools/fabric/gateway_plan.py
    and written, the gateway started and READY, the harness's environment set,
    the state recorded. Every refusal is before the harness exists."""
    binary = binary_path(env, fabric_root)
    version = check_version(binary)
    generator = os.path.join(fabric_root, "tools", "fabric", "gateway_plan.py")
    if not os.path.isfile(generator):
        die("the gateway plan generator (tools/fabric/gateway_plan.py) is not in this checkout. Nothing started.")
    module = _load("fabric_gateway_plan", generator)
    try:
        plan = module.build(agent, provider="anthropic", role=role or None, session=secrets.token_hex(8))
    except Exception as exc:  # noqa: BLE001 — the generator's own refusals and crashes are a launch refusal, said whole
        die(f"the gateway plan cannot be built ({type(exc).__name__}: {exc}). Nothing started.")
    routed = {s["selector"] for s in plan.selectors}
    # What the harness will send: the session model and every tier pin. A model
    # the plan has no route for would be refused by the gateway one request at a time.
    sends = {session_model} | {v for k, v in env.items() if re.fullmatch(r"ANTHROPIC_DEFAULT_[A-Z0-9_]+_MODEL", k) and v}
    missing = sorted(m for m in sends if m and m not in routed)
    if missing:
        skipped = "; ".join(f"{s}" for s in (getattr(plan, "skipped", None) or []))
        die(f"the plan has no route for {', '.join(missing)}, which the harness would send"
            f"{' (skipped: ' + skipped + ')' if skipped else ''}. Nothing started.")
    os.makedirs(state_dir, exist_ok=True)
    plan_path = module.write(plan, os.path.join(state_dir, "gateway-plan.json"))
    gw = start(binary, plan_path, os.path.join(state_dir, "gateway.log"), version, ready_timeout=ready_timeout(env))
    try:
        approve_key(os.path.join(env.get("CLAUDE_CONFIG_DIR") or env.get("HOME", ""), ".claude.json"), gw.key)
    except _Refuse as why:
        stop(gw)
        die(f"{why}. Nothing started.")
    harness_env(gw, env)
    record_state(state_dir, gw)
    return gw
