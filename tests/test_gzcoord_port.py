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


@case("the Python child is gone after TERM, INT, HUP or KILL on its shim")
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
                shim.wait(10)
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


# ── 5. the port's own departures ─────────────────────────────────────

def _replay_env(stub: P.Stub, **extra: str) -> dict:
    return P.cmd_env(CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan", **extra)


def _record_stub(content_json: str) -> P.Stub:
    rec = '{"seq": 5, "id": "r5", "ts": "T", "sender": "x/y", "content": ' + content_json + "}"
    return P.Stub(lambda _h, _m, path, _b: (200, '{"messages": [' + rec + "]}") if path.startswith("/api/messages")
                  else (200, "{}"))


@case("a lone surrogate in a relay record is replaced on stdout, never an encoding error")
def _():
    stub = _record_stub(json.dumps("[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
                                   "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000005\nSUBJECT: s\n\nNOTES:\nA") [:-1]
                        + '\\ud800B\\n"')
    try:
        r = subprocess.run(["node", P.INBOX_CMD, "--replay", "5"], env=_replay_env(stub), capture_output=True, timeout=30)
    finally:
        stub.close()
    eq(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
    ok(b"A?B" in r.stdout, r.stdout[-200:])


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


@case("the relay token is trimmed before the header; one with a line break inside is refused, and never said")
def _():
    seen: list[str | None] = []
    stub = P.Stub(lambda h, _m, _p, _b: (seen.append(h.headers.get("Authorization")), (200, "{}"))[1])
    try:
        eq(_api(stub.url, " tok\r\n"), "{}")
        eq(seen, ["Bearer tok"])
        out = _api(stub.url, "sec\r\nret")
        ok(out.startswith("RelayError None ") and "sec" not in out and "ret" not in out, out)
        eq(len(seen), 1, "nothing was sent")
    finally:
        stub.close()


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
