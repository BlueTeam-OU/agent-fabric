#!/usr/bin/env python3
"""What the Wave 7 port holds beyond the Node it replaced (agent-fabric
ADR-040 §7): where Python's defaults differ from the Node's and the port
must not inherit them, and the port's own departures, decided in review of
#93. test_gzcoord_protocol.py holds the cases ported from the Node, case
for case; this file holds only what had no Node case. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import ast
import contextlib
import glob
import json
import math
import os
import signal
import subprocess
import sys
import time
import traceback
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gzcoord import gzmsg, inbox, send  # noqa: E402
from gzcoord import jsvalues as js  # noqa: E402
import test_gzcoord_protocol as P  # noqa: E402 — its Stub, scratch and command environment

PACKAGE = os.path.join(HERE, "tools", "fabric", "gzcoord")
RUN_PY = os.path.join(PACKAGE, "run.py")
PYTHON = os.environ.get("AGENT_FABRIC_PYTHON") or "/usr/local/bin/fabric-python"
CASES: list[tuple[str, Callable[[], None]]] = []
eq, ok, Failed = P.eq, P.ok, P.Failed


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


# ── 1. digits are ASCII, as they were in the Node ────────────────────

@case("every pattern in the package with a class escape is ASCII: Python's \\d, \\w, \\s and \\b are Unicode")
def _():
    escapes = ("\\d", "\\w", "\\s", "\\b", "\\D", "\\W", "\\S", "\\B")
    bare = []
    for file in sorted(glob.glob(os.path.join(PACKAGE, "*.py"))):
        tree = ast.parse(open(file, encoding="utf-8").read(), file)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                    and node.func.attr in ("compile", "match", "fullmatch", "search", "sub", "split", "findall", "finditer")):
                continue
            pattern = node.args[0] if node.args else None
            text = pattern.value if isinstance(pattern, ast.Constant) and isinstance(pattern.value, str) else \
                ast.unparse(pattern) if pattern is not None else ""
            if not any(e in text for e in escapes):
                continue
            if "re.ASCII" not in ast.unparse(node) and "(?a" not in text:
                bare.append(f"{os.path.basename(file)}:{node.lineno} {text[:60]}")
    eq(bare, [], "patterns with a Unicode class escape")


@case("number() is Number(): no Unicode digit, no sign or space after a radix prefix")
def _():
    for s in ("١٢", "1٢", "0x١٢", "0x 12", "0x+12", "0x-1", "0x1_2", "0x", "0b102", "²"):
        ok(math.isnan(js.number(s)), f"{s!r} is NaN in the Node, {js.number(s)!r} here")
    for s, n in (("0x1F", 31), ("0o17", 15), ("0b101", 5), (" 12 ", 12), ("1e3", 1000)):
        eq(js.number(s), float(n), repr(s))


@case("a hold marker named in non-ASCII digits is no session file")
def _():
    hold = P.scratch("hold-digits-")
    os.chmod(hold, 0o700)
    with open(os.path.join(hold, "١٢.json"), "w", encoding="utf-8") as fh:
        fh.write("{}")
    r = inbox.hold_status(hold)
    eq((r["held"], r["sessions"], r["reason"]), (False, [], inbox.en()("held.no-marker")), json.dumps(r, ensure_ascii=False))


@case("GZCOORD_SHIM_PID in non-ASCII digits is no pid: said in one line, never a traceback")
def _():
    r = subprocess.run([PYTHON, "-I", RUN_PY, "gzmsg", "new-id"], capture_output=True, text=True, timeout=30,
                       env={**os.environ, "GZCOORD_SHIM_PID": "²"})
    eq(r.returncode, 0, r.stderr)
    eq(r.stderr, "gzcoord: not tied to the shim (GZCOORD_SHIM_PID is no pid: '²')\n")
    r = subprocess.run([PYTHON, "-I", RUN_PY, "gzmsg", "new-id"], capture_output=True, text=True, timeout=30,
                       env={k: v for k, v in os.environ.items() if k != "GZCOORD_SHIM_PID"})
    eq((r.returncode, r.stderr), (0, ""), "no shim named: nothing to tie, nothing said")


# ── 2. --taxonomy "" is set ──────────────────────────────────────────

@case("gzmsg validate --taxonomy \"\" uses no catalogue, as the Node's ?? read it")
def _():
    f = P.scratch_file("[GZCOORD/1] INFO\nFROM: develop-qzapp/python-dev-01\nROLE: no-such-role\nPROJECT: agent-fabric\n"
                       "BROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: s\n\nNOTES:\nn\n")
    found = subprocess.run([PYTHON, "-I", RUN_PY, "gzmsg", "validate", f], capture_output=True, text=True, timeout=30, cwd=HERE)
    ok(found.returncode == 1 and "no-such-role" in found.stderr, f"the catalogue walked up to refuses it: {found.stderr}")
    for flags in (["--taxonomy", ""], ["--no-taxonomy"]):
        r = subprocess.run([PYTHON, "-I", RUN_PY, "gzmsg", "validate", f, *flags], capture_output=True, text=True,
                           timeout=30, cwd=HERE)
        eq((r.returncode, r.stdout), (0, "valid GZCOORD/1 message\n"), f"{flags}: {r.stderr}")


@case("a binding recorded as \"\" is that binding, not the path rule's: the Node's ?? read it as set")
def _():
    tax = gzmsg.load_taxonomy(P.CATALOG)
    r = gzmsg.recorded_role(tax, {"agent": "nobody", "binding": "", "role": "no-such-role"})
    ok(r["error"].startswith(' records role "no-such-role"'), r["error"])


# ── 3. the journal never swallows an interrupt ───────────────────────

@case("run_episodic re-raises KeyboardInterrupt and SystemExit; any other exception is the journal's non-answer")
def _():
    saved = inbox._episodic

    def raising(e: BaseException) -> Any:
        class Fake:
            @staticmethod
            def main(_args: list[str]) -> int:
                raise e
        return lambda: Fake
    try:
        for e in (KeyboardInterrupt(), SystemExit(3)):
            inbox._episodic = raising(e)
            try:
                inbox.run_episodic(["record"], "")
            except type(e):
                pass
            else:
                raise Failed(f"{type(e).__name__} became a journal answer")
        inbox._episodic = raising(RuntimeError("disk full"))
        r = inbox.run_episodic(["record"], "")
        eq(r["status"], 1)
        ok("RuntimeError: disk full" in r["stderr"], r["stderr"])
    finally:
        inbox._episodic = saved


# ── 4. the child ends with its shim; presence that cannot be asked ───

def _children(pid: int) -> list[int]:
    out = []
    for stat in glob.glob("/proc/[0-9]*/stat"):
        try:
            with open(stat, encoding="utf-8", errors="replace") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[1]) == pid:
            out.append(int(stat.split("/")[2]))
    return out


def _alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


# The shim's own status says whether it forwarded: an INT forwarded is the
# inbox's KeyboardInterrupt, exit 130; one not forwarded kills the shim.
# The child's end alone cannot say it: PDEATHSIG ends it either way.
SHIM_STATUS = {signal.SIGTERM: -signal.SIGTERM, signal.SIGINT: 130, signal.SIGHUP: -signal.SIGHUP,
               signal.SIGKILL: -signal.SIGKILL}


@case("the Python child is gone after TERM, INT, HUP or KILL on its shim, and the shim ends as the child did")
def _():
    waits: list[int] = []

    def answer(_h, _method, path, _body):
        if path.startswith("/api/wait"):
            waits.append(1)
            return None
        return 200, json.dumps({"messages": []}) if path.startswith("/api/messages") else "{}"
    stub = P.Stub(answer)
    try:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGKILL):
            waits.clear()
            env = P.cmd_env(CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                            AGENT_FABRIC_HOLD_DIR=P.scratch("hold-"))
            shim = subprocess.Popen(["node", P.INBOX_CMD, "--follow"], env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                deadline = time.monotonic() + 15
                while not waits and time.monotonic() < deadline and shim.poll() is None:
                    time.sleep(0.05)
                ok(waits, f"{sig.name}: the watch never reached its long poll")
                kids = _children(shim.pid)
                eq(len(kids), 1, f"{sig.name}: the shim's children")
                os.kill(shim.pid, sig)
                eq(shim.wait(10), SHIM_STATUS[sig], f"{sig.name}: the shim's status")
                deadline = time.monotonic() + 10
                while _alive(kids[0]) and time.monotonic() < deadline:
                    time.sleep(0.05)
                ok(not _alive(kids[0]), f"{sig.name}: the Python child {kids[0]} outlived its shim")
            finally:
                with contextlib.suppress(OSError):
                    os.killpg(shim.pid, signal.SIGKILL)
                shim.wait(10)
    finally:
        stub.close()


@case("presence that times out, or has no node to run, is unavailable — never present, never skipped")
def _():
    meta = {"TO": "h/alpha"}

    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(["node"], 1)

    def no_node(*_a, **_k):
        raise FileNotFoundError(2, "No such file or directory", "node")
    for run, said in ((timeout, "did not finish"), (no_node, "could not run")):
        r = send.check_addressees(meta, "h/me", "tok", run)
        eq(r.get("status", "unset"), None, json.dumps(r))
        ok(said in r["error"], r["error"])
        p = send.asked_presence(meta, "h/me", "tok", run)
        eq([x["kind"] for x in p["problems"]], ["unavailable"], json.dumps(p))
        ok(p["checked"] and said in p["problems"][0]["detail"], json.dumps(p))


# A stand-in for the interpreter (python.mjs runs AGENT_FABRIC_PYTHON): it
# records each signal it is sent, then dies of it. The real child's end
# cannot show forwarding — PDEATHSIG ends it whether or not the shim
# forwarded (review of #93, round 3).
_FAKE_PYTHON = """import os, signal, sys, time
log = os.environ["FAKE_SIGNAL_LOG"]
def got(n, _f):
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(signal.Signals(n).name + "\\n")
    signal.signal(n, signal.SIG_DFL)
    os.kill(os.getpid(), n)
for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(s, got)
with open(log, "a", encoding="utf-8") as fh:
    fh.write("ready\\n")
while True:
    time.sleep(1)
"""


@case("the shim forwards TERM, INT and HUP to its child, which receives each before it ends")
def _():
    d = P.scratch("fake-python-")
    fake = os.path.join(d, "python")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write(f"#!{os.path.realpath(PYTHON)}\n" + _FAKE_PYTHON)
    os.chmod(fake, 0o700)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        log = os.path.join(d, f"{sig.name}.log")
        shim = subprocess.Popen(["node", P.INBOX_CMD, "--follow"], env={**os.environ, "AGENT_FABRIC_PYTHON": fake,
                                "FAKE_SIGNAL_LOG": log}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            deadline = time.monotonic() + 15
            while not (os.path.exists(log) and "ready" in open(log, encoding="utf-8").read()) and time.monotonic() < deadline:
                time.sleep(0.05)
            ok(os.path.exists(log), f"{sig.name}: the stand-in never started")
            os.kill(shim.pid, sig)
            eq(shim.wait(10), -sig, f"{sig.name}: the shim ends as its child did")
            eq(open(log, encoding="utf-8").read().split(), ["ready", sig.name], f"{sig.name}: what the child received")
        finally:
            with contextlib.suppress(OSError):
                os.killpg(shim.pid, signal.SIGKILL)
            shim.wait(10)


# ── 5. the port's own departures ─────────────────────────────────────

def _replay_env(stub: P.Stub, **extra: str) -> dict:
    return P.cmd_env(**{"CLAUDE_BRIDGE_URL": stub.url, "CLAUDE_BRIDGE_AUTH_TOKEN": "tok", "GZCOORD_CHANNEL": "fixture:chan", **extra})


def _record_stub(content_json: str) -> P.Stub:
    rec = '{"seq": 5, "id": "r5", "ts": "T", "sender": "x/y", "content": ' + content_json + "}"
    return P.Stub(lambda _h, _m, path, _b: (200, '{"messages": [' + rec + "]}") if path.startswith("/api/messages")
                  else (200, "{}"))


@case("a lone surrogate in a relay record is U+FFFD on stdout, as the Node wrote it, never an encoding error")
def _():
    stub = _record_stub(json.dumps("[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
                                   "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000005\nSUBJECT: s\n\nNOTES:\nA") [:-1]
                        + '\\ud800B\\n"')
    try:
        r = subprocess.run(["node", P.INBOX_CMD, "--replay", "5"], env=_replay_env(stub), capture_output=True, timeout=30)
    finally:
        stub.close()
    eq(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
    ok("A\ufffdB".encode("utf-8") in r.stdout, f"U+FFFD, as the Node wrote: {r.stdout[-200:]!r}")


@case("output is UTF-8 under a non-UTF-8 locale")
def _():
    have = subprocess.run(["locale", "-a"], capture_output=True, text=True, timeout=10).stdout.split()
    latin = next((x for x in ("en_US", "en_AU", "en_GB", "de_DE", "en_US.iso88591") if x in have), None)
    if latin is None:
        print("       (no non-UTF-8 locale installed here: the lone-surrogate case stands for it)")
        return
    stub = _record_stub(json.dumps("[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
                                   "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000005\nSUBJECT: s\n\nNOTES:\né → ✓\n"))
    try:
        r = subprocess.run(["node", P.INBOX_CMD, "--replay", "5"], env=_replay_env(stub, LC_ALL=latin, LANG=latin),
                           capture_output=True, timeout=30)
    finally:
        stub.close()
    eq(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
    ok("é → ✓".encode("utf-8") in r.stdout, f"{latin}: {r.stdout[-120:]!r}")


_API_CALL = ("import sys; sys.path.insert(0, sys.argv[1]); from gzcoord import inbox\n"
             "try:\n    print(inbox.api(sys.argv[3], '/x', sys.argv[2]))\n"
             "except inbox.RelayError as e:\n    print('RelayError', e.status, e)\n")


def _api(url: str, tok: str = "tok", **env: str) -> str:
    r = subprocess.run([PYTHON, "-I", "-c", _API_CALL, os.path.join(HERE, "tools", "fabric"), url, tok],
                       capture_output=True, text=True, timeout=30, env={**os.environ, **env})
    eq(r.returncode, 0, r.stderr)
    return r.stdout.strip()


@case("the relay is called directly: no proxy from the environment, no redirect followed with the token")
def _():
    seen: list[tuple[str, str | None]] = []

    def answer(h, _method, path, _body):
        seen.append((path, h.headers.get("Authorization")))
        return 200, '{"ok": true}'
    relay = P.Stub(answer)
    elsewhere = P.Stub(answer)
    dead = "http://127.0.0.1:9"   # discard: a proxy that is used fails the call
    try:
        eq(_api(relay.url, http_proxy=dead, HTTP_PROXY=dead, no_proxy="", NO_PROXY=""), "{'ok': True}")
        eq(seen, [("/x", "Bearer tok")])

        seen.clear()
        mover = _Redirect(f"{elsewhere.url}/stolen")
        try:
            out = _api(mover.url)
        finally:
            mover.close()
        ok(out.startswith("RelayError 302 "), out)
        eq(seen, [], "the redirect's target was never called")
    finally:
        relay.close()
        elsewhere.close()


class _Redirect:
    """A relay that answers every call with a 302 to `location`."""

    def __init__(self, location: str):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):  # noqa: N802 — the stdlib's name
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("content-length", "0")
                self.send_header("connection", "close")
                self.end_headers()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@case("every token is trimmed once where it is read; one with a line break or NUL inside is refused, and never said")
def _():
    eq(inbox.checked_token(" tok\r\n"), "tok")
    eq(inbox.checked_token(None), None)
    for bad in ("a\r\nb", "a\nb", "a\0b"):
        try:
            inbox.checked_token(bad)
            raise Failed(f"{bad!r} passed")
        except inbox.TokenRefused as e:
            ok(str(e).startswith("the relay token holds a line break or a NUL; nothing was sent"), str(e))
    home = P.scratch("synced-")
    os.makedirs(os.path.join(home, ".config", "agent-fabric"))
    with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "w", encoding="utf-8") as fh:
        fh.write("export CLAUDE_BRIDGE_AUTH_TOKEN='HEAD\0TAIL'\n")
    try:
        inbox.synced_token(home)
        raise Failed("the synced token, the one re-read after a 401, passed unchecked")
    except inbox.TokenRefused:
        pass
    seen: list[tuple[str, str | None]] = []
    stub = P.Stub(lambda h, _m, path, _b: (seen.append((path, h.headers.get("Authorization"))),
                                           (200, '{"messages": []}') if path.startswith("/api/messages") else (200, "{}"))[1])
    try:
        r = subprocess.run(["node", P.INBOX_CMD, "--history"], env=_replay_env(stub, CLAUDE_BRIDGE_AUTH_TOKEN=" tok\r\n"),
                           capture_output=True, text=True, timeout=30)
        eq(r.returncode, 0, r.stderr)
        api = [a for p, a in seen if p.startswith("/api/")]
        ok(api and all(a == "Bearer tok" for a in api), f"trimmed before the header: {seen}")
    finally:
        stub.close()


@case("send's presence path never sees a token with a line break: refused before presence.mjs is asked, the token unsaid")
def _():
    hits: list[str] = []
    stub = P.Stub(lambda _h, _m, path, _b: (hits.append(path), (200, '{"messages": []}'))[1])
    try:
        env = _replay_env(stub, CLAUDE_BRIDGE_AUTH_TOKEN="SECRET-HEAD\r\nSECRET-TAIL")
        me = gzmsg.whoami()
        f = os.path.join(env["HOME"], "m.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(f"[GZCOORD/1] INFO\nFROM: {me['host']}/{me['agent']}\nROLE: backend-dev\nPROJECT: fixture\n"
                     f"TO: {me['host']}/{me['agent']}\nSUBJECT: s\n\nNOTES:\nn\n")
        r = subprocess.run(["node", P.SEND_CMD, f], env=env, capture_output=True, text=True, timeout=60)
    finally:
        stub.close()
    eq(r.returncode, 1, r.stderr)
    ok("line break or a NUL" in r.stderr, r.stderr)
    ok("SECRET" not in r.stderr + r.stdout, f"the token was said: {r.stderr}")
    eq([h for h in hits if h.startswith("/api/")], [], "nothing reached the relay, the presence request included")


def _synced(home: str, value: str) -> None:
    os.makedirs(os.path.join(home, ".config", "agent-fabric"), exist_ok=True)
    with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "w", encoding="utf-8") as fh:
        fh.write(f"export CLAUDE_BRIDGE_AUTH_TOKEN='{value}'\n")


@case("a 401, then a synced token with a NUL: --follow stops with exit 4 and one line, send exits 3; never 'relay down'")
def _():
    # The token is rotated under a running session: the synced file is
    # written as the first request arrives, then answered 401. token()
    # reads the synced file first, so one there at the start is refused
    # before any request — a different path, exit 0 at a session start.
    home = {"dir": ""}

    def answer(_h, _m, path, _b):
        if not path.startswith("/api/"):
            return 200, "{}"
        _synced(home["dir"], "HEAD\0TAIL")
        return 401, '{"error": "no"}'
    refuse = P.Stub(answer)
    try:
        env = _replay_env(refuse)
        home["dir"] = env["HOME"]
        try:
            r = subprocess.run(["node", P.INBOX_CMD, "--follow"], env=env, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired:
            raise Failed("--follow kept going: the refused token read as a relay that is down") from None
        eq(r.returncode, 4, r.stdout + r.stderr)
        ok("gzcoord inbox: the relay token holds a line break or a NUL" in r.stderr, r.stderr)
        ok("relay down" not in r.stdout + r.stderr and "HEAD" not in r.stdout + r.stderr, r.stderr)
        os.remove(os.path.join(env["HOME"], ".config", "agent-fabric", "secrets.env"))
        me = gzmsg.whoami()
        f = os.path.join(env["HOME"], "m.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(f"[GZCOORD/1] INFO\nFROM: {me['host']}/{me['agent']}\nROLE: backend-dev\nPROJECT: fixture\n"
                     f"BROADCAST: true\nSUBJECT: s\n\nNOTES:\nn\n")
        r = subprocess.run(["node", P.SEND_CMD, f], env={**env, "GZCOORD_JOURNAL": "off"}, capture_output=True, text=True,
                           timeout=60)
        eq(r.returncode, 3, r.stderr)
        ok("send: the relay token holds a line break or a NUL" in r.stderr and "HEAD" not in r.stderr, r.stderr)
    finally:
        refuse.close()


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a case that raises is a failure, reported
            fails += 1
            print(f"  FAIL {name}: {e}")
            if not isinstance(e, Failed):
                traceback.print_exc()
    for d in P.SCRATCH:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_gzcoord_port: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
