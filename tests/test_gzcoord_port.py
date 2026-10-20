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
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
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
    # Every module, its subpackages' too (gzcoord/inbox_parts/).
    for file in sorted(glob.glob(os.path.join(PACKAGE, "**", "*.py"), recursive=True)):
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


# ── 4. presence that cannot be asked ───

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


@case("the presence check runs presence.py isolated (-I) under this interpreter, by an argument list")
def _():
    seen = {}

    def fake(argv, **kw):
        seen["argv"], seen["input"] = argv, kw.get("input")
        return subprocess.CompletedProcess(argv, 0, stdout='{"checked": true, "problems": []}\n', stderr="")
    r = send.check_addressees({"TO": "h/alpha"}, "h/me", "tok", fake)
    eq(seen["argv"], [sys.executable, "-I", os.path.join(HERE, "tools", "fabric", "control", "presence.py"), "check"], str(seen))
    eq(r, {"checked": True, "problems": []})


@case("a command case's relay runtime dir is scratch, never the checkout's workspace: a hosting account's .gzcoord is not read")
def _():
    env = P.cmd_env(CLAUDE_BRIDGE_URL="http://127.0.0.1:1", GZCOORD_CHANNEL="fixture:chan")
    r = subprocess.run([PYTHON, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); from gzcoord import inbox; "
                        "print(inbox.relay_runtime_dir(inbox.integration_config(None)))", os.path.join(HERE, "tools", "fabric")],
                       env=env, capture_output=True, text=True, timeout=30)
    eq(r.returncode, 0, r.stderr)
    runtime = r.stdout.strip()
    ok(runtime.startswith(os.path.realpath(tempfile.gettempdir())) or runtime.startswith(tempfile.gettempdir()), runtime)
    # The checkout's relay runtime is <workspace>/.gzcoord, exactly: a scratch directory may sit
    # inside the workspace (tests/stripped_run.py puts its TMPDIR beside the tree).
    hosted = os.path.join(os.path.dirname(os.path.realpath(HERE)), ".gzcoord")
    ok(os.path.realpath(runtime) != hosted and not os.path.realpath(runtime).startswith(hosted + os.sep),
       f"the checkout's workspace: {runtime}")


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
        r = subprocess.run([P.INBOX_CMD, "--replay", "5"], env=_replay_env(stub), capture_output=True, timeout=30)
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
        r = subprocess.run([P.INBOX_CMD, "--replay", "5"], env=_replay_env(stub, LC_ALL=latin, LANG=latin),
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
        r = subprocess.run([P.INBOX_CMD, "--history"], env=_replay_env(stub, CLAUDE_BRIDGE_AUTH_TOKEN=" tok\r\n"),
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
        r = subprocess.run([P.SEND_CMD, f], env=env, capture_output=True, text=True, timeout=60)
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
            r = subprocess.run([P.INBOX_CMD, "--follow"], env=env, capture_output=True, text=True, timeout=40)
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
        r = subprocess.run([P.SEND_CMD, f], env={**env, "GZCOORD_JOURNAL": "off"}, capture_output=True, text=True,
                           timeout=60)
        eq(r.returncode, 3, r.stderr)
        ok("send: the relay token holds a line break or a NUL" in r.stderr and "HEAD" not in r.stderr, r.stderr)
    finally:
        refuse.close()


# ── the sent ledger is state: under the agent's lock, trimmed whole (ADR-003) ──

@contextlib.contextmanager
def _state_dir(d: str):
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = d
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


@case("record_sent waits for the agent's lock: a second sender never reads the ledger mid-trim")
def _():
    d = P.scratch("ledger-lock-")
    ledger = os.path.join(d, "gzcoord-sent.jsonl")
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, time; sys.path.insert(0, sys.argv[1]); import identity\n"
         "with identity.agent_lock():\n    print('held', flush=True); time.sleep(1.5)",
         os.path.join(HERE, "runtime")],
        env={**os.environ, "AGENT_FABRIC_STATE_DIR": d}, stdout=subprocess.PIPE, text=True)
    try:
        eq(holder.stdout.readline().strip(), "held")
        with _state_dir(d):
            t0 = time.monotonic()
            send.record_sent(ledger, {"id": "m-1", "sha256": "h1", "seq": 1, "at": "T"}, 3)
            waited = time.monotonic() - t0
    finally:
        holder.wait(timeout=10)
    ok(waited >= 1.0, f"record_sent wrote while another process held the lock ({waited:.2f} s)")


@case("a ledger that ends in a fragment: the new entry starts on its own line, readable")
def _():
    d = P.scratch("ledger-fragment-")
    ledger = os.path.join(d, "gzcoord-sent.jsonl")
    whole = js.stringify({"id": "m-0", "sha256": "h0", "seq": 1, "at": "T0"}) + "\n"
    with open(ledger, "w", encoding="utf-8") as fh:
        fh.write(whole + '{"id":"m-cut","sha')   # a send killed mid-append
    with _state_dir(d):
        send.record_sent(ledger, {"id": "m-1", "sha256": "h1", "seq": 2, "at": "T1"}, 3)
    with open(ledger, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    eq(lines[:2], [whole.rstrip("\n"), '{"id":"m-cut","sha'], "what was there is kept as it was")
    eq(json.loads(lines[2]).get("id"), "m-1", "the new entry is a line of its own")
    eq(lines[3:], [""], "one newline ends the file")
    with _state_dir(d):
        send.record_sent(ledger, {"id": "m-2", "sha256": "h2", "seq": 3, "at": "T2"}, 3)
    with open(ledger, encoding="utf-8") as fh:
        eq(fh.read().count("\n\n"), 0, "a whole last line gets no blank line after it")


@case("a trim that cannot replace the ledger leaves it whole: never rewritten in place, never cut")
def _():
    d = P.scratch("ledger-trim-fail-")
    ledger = os.path.join(d, "gzcoord-sent.jsonl")
    with open(ledger, "w", encoding="utf-8") as fh:
        fh.writelines(js.stringify({"id": f"m-{i}", "sha256": f"h{i}", "seq": i, "at": f"T{i}"}) + "\n" for i in range(1004))
    with open(ledger, "rb") as fh:
        before = fh.read()
    real = os.replace

    def refuse(*_a):
        raise OSError(28, "No space left on device")
    os.replace = refuse
    try:
        with _state_dir(d):
            try:
                send.record_sent(ledger, {"id": "m-new", "sha256": "hn", "seq": 9, "at": "Tn"}, 3)
                raise Failed("a trim whose replace failed was not said")
            except send.LedgerNotTrimmed:
                pass   # said as "recorded, not trimmed", never as an unwritten ledger
    finally:
        os.replace = real
    with open(ledger, "rb") as fh:
        after = fh.read()
    eq(after[:len(before)], before, "the ledger was rewritten")
    eq(after[len(before):].count(b"\n"), 1, "only the new line was added")
    eq([x for x in os.listdir(d) if x.startswith(".tmp-")], [], "a temporary was left beside it")

# ── 6. the entry points: bin/gzcoord-inbox, bin/gzcoord-send, bin/gzmsg ─

BIN = os.path.join(HERE, "bin")
ENTRIES = ("gzcoord-inbox", "gzcoord-send", "gzmsg")


def _links() -> str:
    """A directory elsewhere with the entries linked as bootstrap links
    commands into ~/.local/bin: the real path is found from the link."""
    d = P.scratch("links-")
    for name in ENTRIES:
        os.symlink(os.path.join(BIN, name), os.path.join(d, name))
    return d


@case("each bin entry works through a symlink in another directory, from another working directory")
def _():
    links, cwd = _links(), P.scratch("cwd-")
    env = {**P.cmd_env(), "GZCOORD_DEFAULT_LOCALE_ONLY": "1"}
    run = lambda name, *args: subprocess.run([os.path.join(links, name), *args], env=env, cwd=cwd, capture_output=True,
                                             text=True, timeout=60, stdin=subprocess.DEVNULL)
    r = run("gzmsg", "new-id")
    eq((r.returncode, r.stderr), (0, ""))
    ok(len(r.stdout.strip()) == 36, r.stdout)
    r = run("gzcoord-send")
    eq((r.returncode, r.stderr), (1, "usage: gzcoord-send <file>|- [--dry-run] [--force]\n"))
    r = run("gzcoord-inbox", "--replay")
    eq((r.returncode, r.stderr), (1, "usage: gzcoord-inbox --replay <seq|message-id>\n"))


@case("with the interpreter or the module unavailable each entry says one line and exits with its tool's status, never a trace")
def _():
    links = _links()
    lone = P.scratch("lone-")  # an entry with no tools/ beside it: the module cannot load
    os.makedirs(os.path.join(lone, "bin"))
    for name in ENTRIES:
        with open(os.path.join(BIN, name), encoding="utf-8") as src, open(os.path.join(lone, "bin", name), "w", encoding="utf-8") as dst:
            dst.write(src.read())
        os.chmod(os.path.join(lone, "bin", name), 0o755)
    for name, status in (("gzcoord-inbox", 0), ("gzcoord-send", 1), ("gzmsg", 1)):
        for how, path, env in (("no interpreter", os.path.join(links, name), {**os.environ, "AGENT_FABRIC_PYTHON": "/nonexistent/python"}),
                               ("no module", os.path.join(lone, "bin", name), dict(os.environ))):
            r = subprocess.run([path, "x"], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            eq(r.returncode, status, f"{name}, {how}: {r.stderr}")
            eq(len(r.stderr.strip().split("\n")), 1, f"{name}, {how}: {r.stderr}")
            ok("Traceback" not in r.stderr and r.stdout == "", f"{name}, {how}: {r.stderr}")


@case("an entry started with no shim, or with a GZCOORD_SHIM_PID inherited from a shim up the tree, runs")
def _():
    for shim in (None, "1", "²"):
        env = {k: v for k, v in os.environ.items() if k != "GZCOORD_SHIM_PID"}
        if shim is not None:
            env["GZCOORD_SHIM_PID"] = shim
        r = subprocess.run([os.path.join(BIN, "gzmsg"), "new-id"], env=env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        eq((r.returncode, r.stderr), (0, ""), f"GZCOORD_SHIM_PID={shim!r}")


@case("AGENT_FABRIC_PYTHON naming a wrapper that execs the interpreter: the entry execs once and runs (review of #106)")
def _():
    real = os.path.realpath(os.environ.get("AGENT_FABRIC_PYTHON") or "/usr/local/bin/fabric-python")
    if not os.access(real, os.X_OK):
        real = sys.executable
    d = P.scratch("wrapper-")
    wrapper = os.path.join(d, "python")
    with open(wrapper, "w", encoding="utf-8") as fh:
        fh.write(f'#!/bin/sh\nexec "{real}" "$@"\n')
    os.chmod(wrapper, 0o755)
    env = {**os.environ, "AGENT_FABRIC_PYTHON": wrapper}
    env.pop("GZCOORD_ENTRY_EXECED", None)
    r = subprocess.run([os.path.join(BIN, "gzmsg"), "new-id"], env=env, capture_output=True, text=True, timeout=20,
                       stdin=subprocess.DEVNULL)
    eq((r.returncode, r.stderr), (0, ""))
    ok(len(r.stdout.strip()) == 36, r.stdout)


@case("a running `gzcoord-inbox --follow` is found by the session-start hook's watch detection, under the name it is linked as")
def _():
    waits: list[int] = []

    def answer(_h, _method, path, _body):
        if path.startswith("/api/wait"):
            waits.append(1)
            return None
        return 200, json.dumps({"messages": []}) if path.startswith("/api/messages") else "{}"
    stub = P.Stub(answer)
    try:
        d = P.scratch("claude-")
        env = P.cmd_env(CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                        AGENT_FABRIC_HOLD_DIR=P.scratch("hold-"), CMDLINE_OUT=os.path.join(d, "cmdline"),
                        HOOK_PY=os.path.join(HERE, "runtime", "claude-code", "hooks", "session-start.py"),
                        WATCH=os.path.join(_links(), "gzcoord-inbox"))
        # A process named claude is what watch_running looks for above it
        # (a script's comm is its file name; env would re-exec and rename it).
        fake = os.path.join(d, "claude")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/bash\n'
                     'seen() { python3 -c \'import importlib.util as u, sys; s = u.spec_from_file_location("ss", sys.argv[1]); '
                     'm = u.module_from_spec(s); s.loader.exec_module(m); print(m.watch_running())\' "$HOOK_PY"; }\n'
                     'echo "before: $(seen)"\n'
                     '"$WATCH" --follow >/dev/null 2>&1 & w=$!\n'
                     'for _ in $(seq 50); do [ "$(seen)" = True ] && break; sleep 0.2; done\n'
                     'echo "after: $(seen)"\n'
                     'tr "\\0" " " < /proc/$w/cmdline > "$CMDLINE_OUT"\n'
                     'kill $w; wait $w 2>/dev/null; exit 0\n')
        os.chmod(fake, 0o755)
        r = subprocess.run([fake], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        eq(r.stdout.split("\n")[:2], ["before: False", "after: True"], r.stdout + r.stderr)
        with open(os.path.join(d, "cmdline"), encoding="utf-8") as fh:
            cmdline = fh.read()
        ok("gzcoord-inbox --follow" in cmdline, f"the process table reads {cmdline!r}")
    finally:
        stub.close()


# ── --until-delivery: the background watch that ends on a delivery ──

def _wait_stub(pages: list[list[dict]], status: int = 200) -> tuple[P.Stub, list[str]]:
    """A relay whose /api/wait answers the given pages in turn (an empty
    page, after a short pause, once they run out: a quiet long poll)."""
    calls: list[str] = []

    def answer(_h, _m, path, _b):
        if not path.startswith("/api/wait"):
            return 200, "{}"
        calls.append(path)
        if status != 200:
            return status, '{"error": "no"}'
        if len(calls) <= len(pages):
            return 200, json.dumps({"messages": pages[len(calls) - 1]})
        time.sleep(0.3)
        return 200, '{"messages": []}'
    return P.Stub(answer), calls


def _rec(seq: int, subject: str, to: str | None) -> dict:
    addressing = f"TO: {to}\n" if to else "BROADCAST: true\n"
    return {"seq": seq, "id": f"r{seq}", "ts": "T", "sender": "x/y",
            "content": f"[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\n{addressing}"
                       f"MESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000{seq}\nSUBJECT: {subject}\n\nNOTES:\nn\n"}


@case("--until-delivery ignores quiet windows and others' traffic, and exits 0 printing the first delivery addressed here")
def _():
    stub, calls = _wait_stub([[_rec(1, "for-somebody-else", "elsewhere/nobody")], [], [_rec(3, "for-this-session", None)]])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        p = subprocess.Popen([P.INBOX_CMD, "--until-delivery"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        try:
            out, err = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            raise Failed("--until-delivery did not return on a delivery addressed here") from None
        eq(p.returncode, 0, out + err)
        ok("for-this-session" in out, out)
        ok("for-somebody-else" not in out, "a message not addressed here is never printed: " + out)
        ok(len(calls) >= 3, f"it polled past the foreign message and the quiet page ({len(calls)} calls)")
    finally:
        stub.close()


def _arm(env: dict, *flags: str) -> subprocess.Popen:
    return subprocess.Popen([P.INBOX_CMD, *flags], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _wait_started(p: subprocess.Popen, env: dict, deadline: float = 15) -> None:
    """The first watch owns the lock once its file names its pid."""
    lock = glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "agent-fabric", "gzcoord-inbox-*.lock"))
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        lock = glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "agent-fabric", "gzcoord-inbox-*.lock"))
        if lock and open(lock[0]).read().startswith(str(p.pid)):
            return
        time.sleep(0.05)
    raise Failed("the first watch never took its lock")


@case("a second watch exits 0 at once naming the first, which still delivers; the lock frees when the first is gone")
def _():
    # Quiet until the case lets one message through: the first watch must still be watching when the second starts.
    release = threading.Event()
    sent: list[int] = []

    def answer(_h, _m, path, _b):
        if not path.startswith("/api/wait"):
            return 200, "{}"
        if release.is_set() and not sent:
            sent.append(1)
            return 200, json.dumps({"messages": [_rec(5, "late-delivery", None)]})
        time.sleep(0.3)
        return 200, '{"messages": []}'
    stub = P.Stub(answer)
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        first = _arm(env, "--until-delivery")
        try:
            _wait_started(first, env)
            for flag in ("--until-delivery", "--follow"):
                # "At once" is proved by the run returning at all: a second
                # watch that kept watching would last the whole deadline, far
                # past this bound. A wall-clock bound tighter than that only
                # measures how slow the runner's interpreter start is.
                r = subprocess.run([P.INBOX_CMD, flag], env=env, capture_output=True, text=True, timeout=60)
                eq(r.returncode, 0, r.stdout + r.stderr)
                ok(f"a watch is already running (pid {first.pid}, started " in r.stdout and "it ends at its next delivery, at its --deadline (default 1 h 55 min) with the quiet line, or with its session — nothing to kill; do not run it again" in r.stdout, r.stdout)
                ok(r.stdout.count("\n") == 1, "one line: " + r.stdout)
            release.set()
            out, err = first.communicate(timeout=30)
            eq(first.returncode, 0, out + err)
            ok("late-delivery" in out, "the first still delivers: " + out)
        finally:
            first.kill()
            first.communicate()
        # killed or done, the lock is free: a new watch runs (and is stopped again here)
        again = _arm(env, "--until-delivery")
        try:
            try:
                again.wait(timeout=3)
                raise Failed("a watch after the first ended exited: " + again.stdout.read())
            except subprocess.TimeoutExpired:
                pass
            _wait_started(again, env)
        finally:
            again.kill()
            again.communicate()
        killed = _arm(env, "--follow")
        try:
            _wait_started(killed, env)
        finally:
            killed.kill()   # SIGKILL: no cleanup runs, the kernel frees the flock
            killed.communicate()
        third = _arm(env, "--until-delivery")
        try:
            _wait_started(third, env)
            ok(third.poll() is None, "a watch after a killed one runs")
        finally:
            third.kill()
            third.communicate()
    finally:
        stub.close()


@case("a drain, --wait, --history, and a watch flag with --held, --history or --replay take no lock while a watch holds it")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        first = _arm(env, "--until-delivery")
        try:
            _wait_started(first, env)
            for argv in ([], ["--wait", "1"], ["--history"], ["--held", "--until-delivery"], ["--history", "--follow"],
                         ["--replay", "1", "--follow"]):
                r = subprocess.run([P.INBOX_CMD, *argv], env=env, capture_output=True, text=True, timeout=30)
                ok("already running" not in r.stdout + r.stderr, f"{argv}: {r.stdout}{r.stderr}")
        finally:
            first.kill()
            first.communicate()
    finally:
        stub.close()


@case("a pid line that cannot be written leaves the lock held, and release() neither raises nor frees it early")
def _():
    import fcntl
    import resource
    import signal
    from gzcoord.inbox_parts import watchlock
    path = os.path.join(P.scratch("wl-"), "agent-fabric", "x.lock")
    old_lim, old_sig = resource.getrlimit(resource.RLIMIT_FSIZE), signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    lock = watchlock.WatchLock(path)
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, old_lim[1]))   # every write now fails with EFBIG
        ok(lock.acquire(), "the lock is taken though the line cannot be written")
        other = open(path)
        try:
            try:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                raise Failed("a failed pid write gave the lock up")
            except BlockingIOError:
                pass
            lock.release()   # must not raise
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)   # and frees it
        finally:
            other.close()
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, old_lim)
        signal.signal(signal.SIGXFSZ, old_sig)
        lock.release()


@case("a watch whose lock cannot be had says so on stderr and still watches")
def _():
    stub, _calls = _wait_stub([[_rec(1, "delivered-anyway", None)]])
    try:
        # a runtime directory that is a file: the lock's directory cannot be made
        blocked = P.scratch("blocked-")
        open(os.path.join(blocked, "agent-fabric"), "w").close()
        env = _replay_env(stub, GZCOORD_JOURNAL="off", XDG_RUNTIME_DIR=blocked)
        r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=30)
        eq(r.returncode, 0, r.stdout + r.stderr)
        ok("delivered-anyway" in r.stdout, r.stdout)
        ok("no watch lock" in r.stderr, r.stderr)
    finally:
        stub.close()


@case("--until-delivery does not return on a quiet window or a message not addressed here")
def _():
    stub, _calls = _wait_stub([[_rec(1, "for-somebody-else", "elsewhere/nobody")]])
    try:
        p = subprocess.Popen([P.INBOX_CMD, "--until-delivery"], env=_replay_env(stub, GZCOORD_JOURNAL="off"),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            p.wait(timeout=4)
            raise Failed(f"it returned (exit {p.returncode}) with nothing addressed here: {p.stdout.read()}")
        except subprocess.TimeoutExpired:
            pass
        finally:
            p.kill()
            p.communicate()
    finally:
        stub.close()


@case("--until-delivery exits 4 with the reason on stdout when the relay refuses the token; --follow keeps it on stderr")
def _():
    stub, _calls = _wait_stub([], status=401)
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=40)
        eq(r.returncode, 4, r.stdout + r.stderr)
        ok("401" in r.stdout and "relay down" not in r.stdout, "the reason is on stdout, where the session reads it: " + r.stdout)
        f = subprocess.run([P.INBOX_CMD, "--follow"], env=env, capture_output=True, text=True, timeout=40)
        eq(f.returncode, 4, f.stdout + f.stderr)
        ok("401" in f.stderr and "401" not in f.stdout, "--follow is unchanged: the line on stderr")
    finally:
        stub.close()


@case("--until-delivery gives up on an unreachable relay with exit 5 and the reason on stdout, after GZCOORD_UNTIL_DELIVERY_DOWN_S")
def _():
    stub, _calls = _wait_stub([])
    url = stub.url
    stub.close()   # nothing listens there now
    env = _replay_env(stub, GZCOORD_JOURNAL="off", GZCOORD_UNTIL_DELIVERY_DOWN_S="1")
    env["CLAUDE_BRIDGE_URL"] = url
    r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=20)   # under the 30 s retry sleep: the deadline is honoured
    eq(r.returncode, 5, r.stdout + r.stderr)
    ok(url in r.stdout, r.stdout)


@case("--until-delivery: not configured exits 3 with the reason on stdout; a drain stays exit 0 on stderr")
def _():
    env = P.cmd_env(CLAUDE_BRIDGE_URL="", GZCOORD_CHANNEL="", CLAUDE_BRIDGE_AUTH_TOKEN="")
    cwd = P.scratch("nocfg-")
    r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, cwd=cwd, capture_output=True, text=True, timeout=40)
    eq(r.returncode, 3, r.stdout + r.stderr)
    ok(r.stdout.strip() and not r.stderr.strip(), "the reason is on stdout only: " + r.stdout + r.stderr)
    d = subprocess.run([P.INBOX_CMD], env=env, cwd=cwd, capture_output=True, text=True, timeout=40)
    eq(d.returncode, 0, d.stdout + d.stderr)
    ok(not d.stdout.strip() and d.stderr.strip(), "a drain keeps the reason on stderr")


@case("--until-delivery: no token exits 3 with the reason on stdout; a drain stays exit 0")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off", CLAUDE_BRIDGE_AUTH_TOKEN="")
        r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=40)
        eq(r.returncode, 3, r.stdout + r.stderr)
        ok(r.stdout.strip(), "the reason is on stdout: " + r.stderr)
        d = subprocess.run([P.INBOX_CMD], env=env, capture_output=True, text=True, timeout=40)
        eq(d.returncode, 0, d.stdout + d.stderr)
    finally:
        stub.close()


@case("--until-delivery: the last resort is exit 7 with the line on stdout; any other mode keeps exit 0 on stderr")
def _():
    saved = inbox.main

    def boom(_argv):
        raise RuntimeError("unforeseen")
    inbox.main = boom
    # The watch lock is taken in this process: a runtime directory of its own, because a runner's /run/user/<uid> may
    # not be writable and the lock's warning would reach the stderr this case asserts empty (found in the smoke containers).
    saved_runtime = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = P.scratch("runtime-")
    try:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            eq(inbox.run(["--until-delivery"]), 7)
        ok("unforeseen" in out.getvalue() and not err.getvalue(), out.getvalue() + err.getvalue())
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            eq(inbox.run([]), 0)
        ok("unforeseen" in err.getvalue() and not out.getvalue(), out.getvalue() + err.getvalue())
    finally:
        inbox.main = saved
        if saved_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = saved_runtime


@case("--until-delivery: a delivery the journal cannot keep ends it with exit 6 and the held line on stdout, not at the timeout")
def _():
    stub, _calls = _wait_stub([[_rec(1, "for-this-session", None)]])
    try:
        blocker = P.scratch_file("not a directory")
        env = _replay_env(stub, GZCOORD_JOURNAL="off", AGENT_FABRIC_STATE_DIR=os.path.join(blocker, "state"))
        r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=30)
        eq(r.returncode, 6, r.stdout + r.stderr)
        ok("held, not shown" in r.stdout, r.stdout + r.stderr)
    finally:
        stub.close()


@case("--until-delivery: an unreachable relay says watch.relay-gave-up, not 'waiting for it'")
def _():
    stub, _calls = _wait_stub([])
    url = stub.url
    stub.close()
    env = _replay_env(stub, GZCOORD_JOURNAL="off", GZCOORD_UNTIL_DELIVERY_DOWN_S="1")
    env["CLAUDE_BRIDGE_URL"] = url
    r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=20)   # under the 30 s retry sleep: the deadline is honoured
    eq(r.returncode, 5, r.stdout + r.stderr)
    ok("the watch ended" in r.stdout and "waiting for it" not in r.stdout, r.stdout)


QUIET = "gzcoord inbox: quiet for 0 min, nothing delivered; run the watch again\n"


@case("--until-delivery --deadline: a quiet watch exits 0 with exactly the one line and frees the lock for the next watch")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        t0 = time.monotonic()
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "3"], env=env, capture_output=True, text=True, timeout=30)
        eq(r.returncode, 0, r.stdout + r.stderr)
        eq(r.stdout, QUIET)
        ok(time.monotonic() - t0 < 15, "it ends near its deadline")
        again = _arm(env, "--until-delivery")
        try:
            _wait_started(again, env)
            ok(again.poll() is None, "the watch after the quiet one runs")
        finally:
            again.kill()
            again.communicate()
    finally:
        stub.close()


@case("--until-delivery --deadline: a delivery before the deadline is printed as without it")
def _():
    stub, _calls = _wait_stub([[_rec(1, "in-time", None)]])
    try:
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "60"], env=_replay_env(stub, GZCOORD_JOURNAL="off"),
                           capture_output=True, text=True, timeout=30)
        eq(r.returncode, 0, r.stdout + r.stderr)
        ok("in-time" in r.stdout and "quiet for" not in r.stdout, r.stdout)
    finally:
        stub.close()


@case("--deadline: not a positive number, or without --until-delivery, is a usage line on stderr and exit 1")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        for argv in (["--until-delivery", "--deadline", "0"], ["--until-delivery", "--deadline", "-5"],
                     ["--until-delivery", "--deadline", "soon"], ["--until-delivery", "--deadline"],
                     ["--until-delivery", "--deadline", "Infinity"], ["--follow", "--deadline", "5"], ["--deadline", "5"]):
            r = subprocess.run([P.INBOX_CMD, *argv], env=env, capture_output=True, text=True, timeout=30)
            eq(r.returncode, 1, f"{argv}: {r.stdout}{r.stderr}")
            ok("--deadline takes a number of seconds" in r.stderr and r.stdout == "", f"{argv}: {r.stdout}{r.stderr}")
    finally:
        stub.close()


@case("--deadline defaults to 6900 s, under the harness's 7200 s cap")
def _():
    from gzcoord import inbox
    eq(inbox.DEFAULT_DEADLINE_S, 6900.0)


@case("a hold that outlasts the deadline ends wait_loop; before it, the hold keeps waiting")
def _():
    from gzcoord.inbox_parts.watch import wait_loop
    naps: list[float] = []

    def nap(ms: float) -> None:
        naps.append(ms)
        if len(naps) > 500:   # a deadline that is ignored must fail the case, not hang the suite
            raise Failed("the hold outlasted its deadline")
        time.sleep(0.01)
    never = lambda *_a: (_ for _ in ()).throw(Failed("a held watch fetched"))   # noqa: E731
    res = wait_loop(never, never, 3600, held=lambda: True, sleep=nap, deadline=time.monotonic() - 1)
    ok(res["delivered"] is False and not naps, f"{res} {naps}")
    end = time.monotonic() + 0.2
    res = wait_loop(never, never, 3600, held=lambda: True, sleep=nap, deadline=end)
    ok(naps and time.monotonic() >= end and res["delivered"] is False, f"it waited out the hold: {naps}")


@case("a watch killed by SIGTERM frees the lock; a mark left by a dead pid is taken over with a line on stderr, a live one is not reported")
def _():
    import signal
    from gzcoord.inbox_parts import watchlock
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        first = _arm(env, "--until-delivery")
        try:
            _wait_started(first, env)
            first.send_signal(signal.SIGTERM)
            first.communicate(timeout=10)
        finally:
            first.kill()
        again = _arm(env, "--until-delivery")
        try:
            _wait_started(again, env)
            ok(again.poll() is None, "a watch after a SIGTERMed one runs")
        finally:
            again.kill()
            again.communicate()
    finally:
        stub.close()
    base = P.scratch("mark-")
    path = os.path.join(base, "agent-fabric", "x.lock")
    os.makedirs(os.path.dirname(path))
    for pid, gone in ((2**22 + 1, True), (os.getppid(), False)):   # beyond pid_max, and a live control
        open(path, "w").write(f"{pid}\n2026-10-16T00:00:00Z\n")
        lock = watchlock.WatchLock(path)
        try:
            ok(lock.acquire(), "the lock is free")
            eq(lock.took_over, str(pid) if gone else None)
        finally:
            lock.release()


def _mark_path(env: dict) -> str:
    lock = glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "agent-fabric", "gzcoord-inbox-*.lock"))
    ok(len(lock) == 1, f"one lock file: {lock}")
    return lock[0]


@case("--deadline: a relay that accepts and never answers still ends the watch near its deadline")
def _():
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    held_open: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                held_open.append(srv.accept()[0])
            except OSError:
                pass
    th = threading.Thread(target=accept, daemon=True)
    th.start()
    try:
        env = P.cmd_env(**{"CLAUDE_BRIDGE_URL": f"http://127.0.0.1:{srv.getsockname()[1]}", "CLAUDE_BRIDGE_AUTH_TOKEN": "tok",
                           "GZCOORD_CHANNEL": "fixture:chan", "GZCOORD_JOURNAL": "off"})
        t0 = time.monotonic()
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "2"], env=env, capture_output=True, text=True, timeout=40)
        eq(r.returncode, 0, r.stdout + r.stderr)
        eq(r.stdout, QUIET)
        ok(time.monotonic() - t0 < 20, "the unanswered request is not waited out")
    finally:
        stop.set()
        th.join()
        for c in held_open:
            c.close()
        srv.close()


@case("--deadline: a relay that refuses connections ends the watch at the deadline, not after the 30 s retry sleep")
def _():
    stub, _calls = _wait_stub([])
    url = stub.url
    stub.close()   # nothing listens there now: every try is refused at once
    env = _replay_env(stub, GZCOORD_JOURNAL="off")   # the give-up bound stays at its 900 s, so only the deadline can end it
    env["CLAUDE_BRIDGE_URL"] = url
    t0 = time.monotonic()
    r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "2"], env=env, capture_output=True, text=True, timeout=20)
    eq(r.returncode, 0, r.stdout + r.stderr)
    eq(r.stdout, QUIET)
    ok(time.monotonic() - t0 < 10, "the retry sleep is cut at the deadline")


@case("an invalid --deadline neither rewrites the mark nor is answered with another watch's refusal line")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        first = _arm(env, "--until-delivery")
        try:
            _wait_started(first, env)
            before = open(_mark_path(env)).read()
            r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "0"], env=env, capture_output=True, text=True, timeout=30)
            eq(r.returncode, 1, r.stdout + r.stderr)
            ok("--deadline takes a number of seconds" in r.stderr and r.stdout == "", r.stdout + r.stderr)
            eq(open(_mark_path(env)).read(), before)
        finally:
            first.kill()
            first.communicate()
    finally:
        stub.close()


@case("the start says so when a killed watch left its mark, and not after a watch that ended by itself")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        line = "taking over the watch mark of pid"
        quiet = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "1"], env=env, capture_output=True, text=True, timeout=30)
        eq(quiet.stdout, QUIET)
        again = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "1"], env=env, capture_output=True, text=True, timeout=30)
        ok(line not in again.stderr, "a watch that ended by itself leaves no mark: " + again.stderr)
        first = _arm(env, "--until-delivery")
        try:
            _wait_started(first, env)
        finally:
            first.kill()   # SIGKILL: the pid stays in the file
            first.communicate()
        killed = first.pid
        after = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "1"], env=env, capture_output=True, text=True, timeout=30)
        ok(f"{line} {killed}, which is gone" in after.stderr, after.stderr)
        eq(after.stdout, QUIET)
    finally:
        stub.close()


# ── a watch ends with its session (2026-10-20) ───────────────────────

def _fake_proc(root: str, procs: dict[int, tuple]) -> str:
    """A /proc of the given processes {pid: (comm, ppid, state, start[, cmdline])}: the files session.py reads."""
    for pid, spec in procs.items():
        comm, ppid, state, start = spec[:4]
        d = os.path.join(root, str(pid))
        os.makedirs(d, exist_ok=True)
        # pid (comm) state ppid pgrp session tty tpgid flags minflt cminflt majflt cmajflt utime stime cutime cstime prio nice threads itreal start
        rest = [state, str(ppid)] + ["0"] * 17 + [str(start)]
        open(os.path.join(d, "stat"), "w").write(f"{pid} ({comm}) " + " ".join(rest) + " 0 0\n")
        open(os.path.join(d, "cmdline"), "wb").write(b"\0".join(a.encode() for a in (spec[4] if len(spec) > 4 else [comm])) + b"\0")
    return root


@case("session.py reads a session from /proc: the nearest claude through shells, else the parent; a reused pid, a zombie and a dead parent are an ended session")
def _():
    from gzcoord.inbox_parts import session as S
    root = _fake_proc(P.scratch("proc-"), {
        1: ("systemd", 0, "S", 1), 50: ("claude", 1, "S", 500), 60: ("bash", 50, "S", 600), 61: ("bash", 60, "S", 610), 70: ("fabric-python", 61, "S", 700),
        80: ("python3", 1, "S", 800), 81: ("python3", 80, "S", 810),
        90: ("bash", 1, "S", 900), 91: ("fabric-python", 90, "S", 910)})
    eq(S.nearest_claude(70, root).pid, 50)
    cur = S.current(root, pid=70, ppid=61)
    eq((cur.pid, cur.start, cur.parent, cur.kind), (50, "500", 61, "claude"))
    eq(S.current(root, pid=81, ppid=80).kind, "parent")
    eq(S.current(root, pid=91, ppid=90).kind, "detached")
    ok(S.reparented(91, root) and not S.reparented(81, root) and not S.reparented(70, root), "init through shells only; a python parent is not; claude above is not")
    ok(not S.reparented(424242, root), "a process /proc does not show is not read as orphaned")
    ok(not S.ended(cur, 70, root) and not S.gone(cur, root, pid=70, ppid=61), "the session is there")
    ok(S.gone(cur, root, pid=70, ppid=1), "the watch's parent changed")
    for label, change in (("gone", None), ("another process under the pid", ("claude", 1, "S", 999)), ("a zombie", ("claude", 1, "Z", 500))):
        again = _fake_proc(P.scratch("proc-"), {1: ("systemd", 0, "S", 1), 61: ("bash", 1, "S", 610), 70: ("fabric-python", 61, "S", 700),
                                                **({50: change} if change else {})})
        ok(S.ended(cur, 70, again) and S.gone(cur, again, pid=70, ppid=61), f"the session is {label}")
    parent_kind = S.Session(80, "800", 80, "parent")
    ok(not S.ended(parent_kind, 81, root), "a parent session that is alive, the watch under it")
    orphan = _fake_proc(P.scratch("proc-"), {1: ("systemd", 0, "S", 1), 80: ("bash", 1, "S", 800), 81: ("fabric-python", 80, "S", 810)})
    ok(S.ended(parent_kind, 81, orphan), "the wrapper shell lives on, hanging from init: the session it stood for is gone")
    ok(not S.ended(S.Session(80, "800", 80, "detached"), 81, orphan), "a detached watch is ended by its parent's death only")
    eq(S.Session.of(["50", "500", "claude", ""]), S.Session(50, "500", 0, "claude"))
    ok(S.Session.of(["50"]) is None and S.Session.of(["x", "1", "claude"]) is None and S.Session.of(["5", "1", "other"]) is None, "a malformed or short record is no session")
    for args, want in (([PYTHON, "-I", "/x/bin/gzcoord-inbox", "--until-delivery"], True), (["python3", "/x/tools/fabric/gzcoord/inbox.py", "--follow"], True),
                       ([PYTHON, "/x/bin/gzcoord-inbox"], False), ([PYTHON, "/x/bin/gzcoord-inbox", "--replay", "5", "--follow"], False),
                       (["sleep", "60", "--until-delivery"], False), (["bash", "-c", "x", "y", "z", "gzcoord-inbox", "--follow"], False)):
        r2 = _fake_proc(P.scratch("proc-"), {7: ("fabric-python", 1, "S", 1, args)})
        eq(S.is_inbox(7, r2), want)


@case("lock_holder reads the pid that owns the flock from /proc/locks, not a waiter's, and not a pid the namespace cannot name")
def _():
    from gzcoord.inbox_parts import watchlock
    f = os.path.join(P.scratch("lk-"), "x.lock")
    open(f, "w").close()
    st = os.stat(f)
    dev = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    locks = os.path.join(P.scratch("lk-"), "locks")

    def holder(text: str):
        open(locks, "w").write(text)
        return watchlock.lock_holder(f, locks)
    eq(holder(f"1: FLOCK  ADVISORY  WRITE 4242 {dev} 0 EOF\n"), 4242)
    eq(holder(f"1: -> FLOCK  ADVISORY  WRITE 99 {dev} 0 EOF\n2: FLOCK  ADVISORY  WRITE 4242 {dev} 0 EOF\n"), 4242)
    ok(holder(f"1: FLOCK  ADVISORY  WRITE 4242 00:00:1 0 EOF\n") is None, "another file's lock")
    ok(holder(f"1: FLOCK  ADVISORY  WRITE 0 {dev} 0 EOF\n") is None, "pid 0 is a holder in another pid namespace")
    ok(holder(f"1: POSIX  ADVISORY  WRITE 4242 {dev} 0 EOF\n") is None, "a POSIX lock is not the flock")
    ok(watchlock.lock_holder(f, os.path.join(locks, "absent")) is None, "no /proc/locks")


def _orphan_world(file_lines: list[str], procs: dict, holder: int = 100) -> tuple[list, list, str]:
    """(calls, result, stderr) of end_orphan on a fake /proc and a fake /proc/locks naming `holder` as the holder."""
    from gzcoord.inbox_parts import watchlock
    base = P.scratch("orph-")
    path = os.path.join(base, "x.lock")
    open(path, "w").close()
    st = os.stat(path)
    locks = os.path.join(base, "locks")
    open(locks, "w").write(f"1: FLOCK  ADVISORY  WRITE {holder} {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino} 0 EOF\n")
    root = _fake_proc(os.path.join(base, "proc"), procs)
    sent: list = []
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        res = watchlock.end_orphan(path, file_lines, root, locks, kill=lambda pid, sig: sent.append((pid, sig)))
    return sent, res, err.getvalue()


@case("end_orphan signals a holder by its pid, once, and only a gzcoord-inbox watch of this login whose session is gone")
def _():
    import signal
    watch = [PYTHON, "-I", "/x/bin/gzcoord-inbox", "--until-delivery"]
    base = {1: ("systemd", 0, "S", 1), 90: ("claude", 1, "S", 900), 91: ("bash", 90, "S", 910)}
    # a recorded session that is gone (pid 55 is not there)
    sent, res, err = _orphan_world(["100", "T", "55", "550", "claude"], {**base, 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([(100, signal.SIGTERM)], True))
    ok("pid 100" in err and "session, pid 55, has ended" in err, err)
    # the same record with the session alive: refused as before, nothing signalled
    sent, res, _ = _orphan_world(["100", "T", "90", "900", "claude"], {**base, 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([], False))
    # the session's pid reused by another process
    sent, res, _ = _orphan_world(["100", "T", "90", "111", "claude"], {**base, 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([(100, signal.SIGTERM)], True))
    # a holder that is no watch (a sleeper, a drain, a replay) is never signalled, though its session is gone
    for args in (["sleep", "60"], [PYTHON, "-I", "/x/bin/gzcoord-inbox"], [PYTHON, "-I", "/x/bin/gzcoord-inbox", "--replay", "5", "--follow"]):
        sent, res, _ = _orphan_world(["100", "T", "55", "550", "claude"], {**base, 100: ("fabric-python", 91, "S", 1000, args)})
        eq((sent, res), ([], False), args)
    # a file of two lines (an older watch): judged by the holder hanging from init or systemd through shells only
    gone_tree = {1: ("systemd", 0, "S", 1), 91: ("bash", 1, "S", 910), 100: ("fabric-python", 91, "S", 1000, watch)}
    sent, res, _ = _orphan_world(["100", "T"], gone_tree)
    eq((sent, res), ([(100, signal.SIGTERM)], True))
    sent, res, _ = _orphan_world(["100", "T"], {**base, 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([], False))
    sent, res, _ = _orphan_world(["100", "T"], {1: ("systemd", 0, "S", 1), 91: ("python3", 1, "S", 910), 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([], False), "a parent that is not a shell is a session of its own")
    # a file naming another pid than the one that owns the flock is stale: its session lines are not the holder's
    sent, res, _ = _orphan_world(["77", "T", "55", "550", "claude"], {**base, 100: ("fabric-python", 91, "S", 1000, watch)})
    eq((sent, res), ([], False))
    # nothing to judge: the holder is not in /proc
    sent, res, _ = _orphan_world(["100", "T", "55", "550", "claude"], base)
    eq((sent, res), ([], False))
    # this process owns the flock (a second take in one process): never signalled, whatever its record says
    me = os.getpid()
    sent, res, _ = _orphan_world([str(me), "T", "55", "550", "claude"], {**base, me: ("fabric-python", 91, "S", 1000, watch)}, holder=me)
    eq((sent, res), ([], False))


_HOLDER = r"""
import fcntl, os, sys, time
sys.path.insert(0, sys.argv[1])
from gzcoord.inbox_parts import watchlock, session
path, mode, spid, sstart, kind = sys.argv[3:8]
if mode == "new-deaf":
    import signal
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode.startswith("new"):
    lock = watchlock.WatchLock(path)
    assert lock.acquire(session.Session(int(spid), sstart, 0, kind))
else:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n2026-10-20T00:00:00Z\n".encode())
print("READY", flush=True)
time.sleep(300)
"""
_SIM = r"""
import ctypes, subprocess, sys
ctypes.CDLL(None).prctl(15, sys.argv[1].encode(), 0, 0, 0)   # PR_SET_NAME: what /proc shows as the process's name
sys.exit(subprocess.call(sys.argv[2:]))
"""


def _spawn_holder(name: str, mode: str, lock: str, session_pid: int = 0, session_start: str = "", kind: str = "claude",
                  parent_comm: str | None = None) -> subprocess.Popen:
    """A process that owns the flock on `lock` and looks like a gzcoord-inbox watch (`name` is its script), optionally under a
    stand-in parent that /proc names `parent_comm`."""
    d = P.scratch("holder-")
    script = os.path.join(d, name)
    open(script, "w").write(_HOLDER)
    argv = [sys.executable, script, os.path.join(HERE, "tools", "fabric"), "--until-delivery", lock, mode, str(session_pid), session_start, kind]
    if parent_comm:
        sim = os.path.join(d, "sim.py")
        open(sim, "w").write(_SIM)
        argv = [sys.executable, sim, parent_comm, *argv]
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
    line = p.stdout.readline()
    if line.strip() != "READY":
        p.kill()
        raise Failed(f"the holder did not start: {line!r}")
    return p


def _dead_session() -> tuple[int, str]:
    """(pid, start time) of a process that existed and is gone and reaped."""
    from gzcoord.inbox_parts import session as S
    p = subprocess.Popen(["sleep", "60"])
    start = S.read_proc(p.pid).start
    p.kill()
    p.wait()
    return p.pid, start


def _take(lock_dir: str, session: Any = None, wait_s: float = 5.0) -> tuple[Any, str, str]:
    """take_or_report in this process on a lock directory of its own: (lock or None, stdout, stderr)."""
    from gzcoord.inbox_parts import watchlock
    saved = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = lock_dir
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            lock = watchlock.take_or_report("fixture-login", session, wait_s)
    finally:
        if saved is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = saved
    return lock, out.getvalue(), err.getvalue()


def _reap(*procs: subprocess.Popen) -> None:
    for p in procs:
        p.kill()
        p.wait()
        p.stdout.close()


@case("an orphaned holder is ended by its pid and the new watch takes the lock, naming both pids; a holder whose session is alive is refused as before")
def _():
    import signal
    from gzcoord.inbox_parts import session as S, watchlock
    me = S.read_proc(os.getpid())
    run_dir = P.scratch("run-")
    lock_file = watchlock.lock_path("fixture-login", run_dir)
    dead_pid, dead_start = _dead_session()
    orphan = _spawn_holder("gzcoord-inbox", "new", lock_file, dead_pid, dead_start)
    try:
        mine = S.Session(os.getpid(), me.start, os.getppid(), "parent")
        lock, out, err = _take(run_dir, mine)
        try:
            ok(lock is not None and lock.acquired, f"the lock was taken: {out!r} {err!r}")
            ok(f"pid {orphan.pid}" in err and f"pid {os.getpid()}" in err and "SIGTERM" in err, err)
            eq(out, "")
            eq(orphan.wait(timeout=10), -signal.SIGTERM)
            lines = open(lock_file).read().split("\n")
            eq(lines[0], str(os.getpid()))
            eq(lines[2:5], [str(os.getpid()), me.start, "parent"], "the file records the session after the pid and the start time")
            # the lock is now held by a watch whose session is alive: a third one is refused, the second is not signalled
            third, out3, err3 = _take(run_dir, mine)
            ok(third is None and f"a watch is already running (pid {os.getpid()}, started " in out3 and "SIGTERM" not in err3, out3 + err3)
        finally:
            lock.release()
    finally:
        _reap(orphan)
    live = _spawn_holder("gzcoord-inbox", "new", lock_file, os.getpid(), me.start)
    try:
        none, out, err = _take(run_dir, S.Session(os.getpid(), me.start, os.getppid(), "parent"), wait_s=1.0)
        ok(none is None and f"a watch is already running (pid {live.pid}, started " in out, out + err)
        ok(live.poll() is None and "SIGTERM" not in err, "the live holder was not signalled: " + err)
    finally:
        _reap(live)


@case("a lock file of two lines (an older watch) is judged by the holder's parent: under a shell-less systemd it is taken over, under any other live parent it is refused")
def _():
    import signal
    from gzcoord.inbox_parts import session as S, watchlock
    me = S.read_proc(os.getpid())
    mine = S.Session(os.getpid(), me.start, os.getppid(), "parent")
    for parent_comm, taken in (("systemd", True), ("python3", False)):
        run_dir = P.scratch("run-")
        lock_file = watchlock.lock_path("fixture-login", run_dir)
        old = _spawn_holder("gzcoord-inbox", "old", lock_file, parent_comm=parent_comm)
        try:
            ok(len(open(lock_file).read().strip().split("\n")) == 2, "the older watch wrote two lines")
            lock, out, err = _take(run_dir, mine, wait_s=3.0)
            try:
                if taken:
                    # the stand-in parent exits with its child's status, a signal as 256 - n
                    ok(lock is not None and lock.acquired and old.wait(timeout=10) in (-signal.SIGTERM, 256 - signal.SIGTERM), f"taken over: {out!r} {err!r}")
                else:
                    ok(lock is None and "a watch is already running" in out and old.poll() is None, f"refused: {out!r} {err!r}")
            finally:
                if lock is not None:
                    lock.release()
        finally:
            _reap(old)


@case("a holder that is not a gzcoord-inbox is never signalled, though it owns the lock with a session that is gone; the same holder under the right name is ended")
def _():
    import signal
    from gzcoord.inbox_parts import session as S, watchlock
    me = S.read_proc(os.getpid())
    mine = S.Session(os.getpid(), me.start, os.getppid(), "parent")
    dead_pid, dead_start = _dead_session()
    for name, ended in (("some-other-tool", False), ("gzcoord-inbox", True)):
        run_dir = P.scratch("run-")
        lock_file = watchlock.lock_path("fixture-login", run_dir)
        holder = _spawn_holder(name, "new", lock_file, dead_pid, dead_start)
        try:
            lock, out, err = _take(run_dir, mine, wait_s=3.0)
            try:
                if ended:
                    ok(lock is not None and holder.wait(timeout=10) == -signal.SIGTERM, f"{out!r} {err!r}")
                else:
                    ok(lock is None and holder.poll() is None and "SIGTERM" not in err, f"{out!r} {err!r}")
            finally:
                if lock is not None:
                    lock.release()
        finally:
            _reap(holder)


def S_alive(pid: int) -> bool:
    from gzcoord.inbox_parts import session as S
    p = S.read_proc(pid)
    return p is not None and p.state != "Z"


@case("a holder that ignores SIGTERM is waited for a bounded time, then refused as a holder: the line says so and the lock is not taken")
def _():
    from gzcoord.inbox_parts import session as S, watchlock
    me = S.read_proc(os.getpid())
    run_dir = P.scratch("run-")
    lock_file = watchlock.lock_path("fixture-login", run_dir)
    dead_pid, dead_start = _dead_session()
    deaf = _spawn_holder("gzcoord-inbox", "new-deaf", lock_file, dead_pid, dead_start)
    try:
        t0 = time.monotonic()
        lock, out, err = _take(run_dir, S.Session(os.getpid(), me.start, os.getppid(), "parent"), wait_s=1.0)
        ok(lock is None and f"a watch is already running (pid {deaf.pid}, started " in out, out + err)
        ok("did not release the lock in time" in err and "SIGTERM" in err and 1.0 <= time.monotonic() - t0 < 30, err)
        ok(deaf.poll() is None, "the holder that would not end is still the holder")
    finally:
        _reap(deaf)


def _wait_lock_lines(env: dict, n: int, deadline: float = 20) -> list[str]:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        found = glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "agent-fabric", "gzcoord-inbox-*.lock"))
        lines = open(found[0]).read().split("\n") if found else []
        if len([ln for ln in lines if ln]) >= n:
            return lines
        time.sleep(0.05)
    raise Failed("the watch never wrote its session into the lock file")


def _wait_gone(p: subprocess.Popen, what: str, deadline: float = 30) -> tuple[str, str]:
    try:
        return p.communicate(timeout=deadline)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise Failed(what) from None


@case("a watch whose claude is gone ends at once with one line and exit 0, though the shell that runs it lives on; while claude is there it keeps watching")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        d = P.scratch("sim-")
        sim = os.path.join(d, "sim.py")
        open(sim, "w").write(_SIM)
        # claude (a stand-in the kernel names `claude`) > sh > the watch: the harness's tree
        claude = subprocess.Popen([sys.executable, sim, "claude", sys.executable, sim, "sh", P.INBOX_CMD, "--until-delivery"],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            lines = _wait_lock_lines(env, 5)
            eq(lines[2:5], [str(claude.pid), lines[3], "claude"], "the watch serves the nearest claude above it, not the shell")
            ok(lines[3].isdigit(), "with its start time")
            time.sleep(2.5)
            eq(claude.poll(), None, "the session is alive")
            ok(S_alive(int(lines[0])), "the watch keeps watching while claude is there")
            watch = int(lines[0])
            claude.kill()   # the session ends; the shell it started stays, reparented
            out, err = _wait_gone(claude, "the watch outlived its claude")
            ok(not S_alive(watch), "the watch is gone")
            eq(out, f"gzcoord-inbox: the session this watch served (pid {claude.pid}) has ended; the watch ends with it\n", out + err)
        finally:
            claude.kill()
            claude.communicate()
    finally:
        stub.close()


@case("a watch ends when its parent changes: the shell that ran it dies and the session it served is not what it started under")
def _():
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        d = P.scratch("sim-")
        sim = os.path.join(d, "sim.py")
        open(sim, "w").write(_SIM)
        shell = subprocess.Popen([sys.executable, sim, "sh", P.INBOX_CMD, "--follow"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            lines = _wait_lock_lines(env, 5)
            watch = int(lines[0])
            time.sleep(1.5)
            ok(S_alive(watch), "watching")
            shell.kill()
            shell.wait()
            end = time.monotonic() + 30
            while S_alive(watch) and time.monotonic() < end:
                time.sleep(0.1)
            ok(not S_alive(watch), "the watch left with its parent")
            out, err = shell.communicate(timeout=10)
            ok("has ended; the watch ends with it" in out, out + err)
        finally:
            shell.kill()
            shell.communicate()
    finally:
        stub.close()


@case("a new watch ends an orphaned older one it finds holding the lock, through the real command")
def _():
    from gzcoord.inbox_parts import session as S
    stub, _calls = _wait_stub([])
    try:
        env = _replay_env(stub, GZCOORD_JOURNAL="off")
        first = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "1"], env=env, capture_output=True, text=True, timeout=60)
        eq(first.stdout, QUIET)
        lock_file = _mark_path(env)
        dead_pid, dead_start = _dead_session()
        orphan = _spawn_holder("gzcoord-inbox", "new", lock_file, dead_pid, dead_start)
        try:
            r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "1"], env=env, capture_output=True, text=True, timeout=60)
            eq((r.returncode, r.stdout), (0, QUIET), r.stdout + r.stderr)
            ok(f"the watch of pid {orphan.pid} outlived its session" in r.stderr and "SIGTERM" in r.stderr, r.stderr)
            eq(orphan.wait(timeout=10), -signal.SIGTERM)
        finally:
            _reap(orphan)
    finally:
        stub.close()


@case("wait_loop ends on session_gone before it fetches, while a slice is out, and when a page lands with it, acknowledging nothing")
def _():
    from gzcoord.inbox_parts.watch import wait_loop
    never = lambda *_a: (_ for _ in ()).throw(Failed("fetched or acknowledged after the session ended"))   # noqa: E731
    res = wait_loop(never, never, 3600, session_gone=lambda: True)
    ok(res.get("sessionEnded") and res["delivered"] is False, str(res))
    # a slice in flight when the session goes: abandoned, no acknowledgement
    started = threading.Event()
    acked: list = []

    def slow(_slice: int, abort: threading.Event) -> Any:
        started.set()
        abort.wait(20)
        return {"messages": []}
    t0 = time.monotonic()
    res = wait_loop(slow, lambda i: acked.append(i), 3600, session_gone=lambda: started.is_set(), hold_poll_ms=50)
    ok(res.get("sessionEnded") and not acked and time.monotonic() - t0 < 10, f"{res} {acked}")
    # a page that landed as the session ended: the message is not acknowledged (the relay shows it to the next watch) nor journaled
    msg = {"id": "r1", "seq": 1, "content": "[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
                                            "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: s\n\nNOTES:\nA\n"}
    calls = {"n": 0}

    def gone_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1
    journaled: list = []
    res = wait_loop(lambda _s, _a: {"messages": [msg]}, lambda i: acked.append(i), 3600, for_me_fn=lambda m: True,
                    journal=lambda recs: journaled.append(recs) or {"ok": True}, session_gone=gone_after_first)
    ok(res.get("sessionEnded") and not acked and not journaled and res["delivered"] is False, f"{res} {acked} {journaled}")
    # the control: the same page with the session alive is delivered and acknowledged
    res = wait_loop(lambda _s, _a: {"messages": [msg]}, lambda i: acked.append(i), 3600, for_me_fn=lambda m: True,
                    journal=lambda recs: {"ok": True}, session_gone=lambda: False)
    ok(res["delivered"] and acked == ["r1"] and not res.get("sessionEnded"), f"{res} {acked}")


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
