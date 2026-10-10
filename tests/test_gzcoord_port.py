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
import subprocess
import sys
import tempfile
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
    r = subprocess.run([P.INBOX_CMD, "--until-delivery"], env=env, capture_output=True, text=True, timeout=90)
    eq(r.returncode, 5, r.stdout + r.stderr)
    ok(url in r.stdout, r.stdout)


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
