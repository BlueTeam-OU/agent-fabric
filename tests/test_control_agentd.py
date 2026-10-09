#!/usr/bin/env python3
"""Tests for tools/fabric/control/agentd.py, the port of runtime/control/agentd.mjs
(ADR-040 Wave 8, step s6).

agentd.test.mjs's cases are ported case for case. The daemon cases run the
real `python3 tools/fabric/control/agentd.py` as a subprocess against a fake
relay in this process, with a minimal explicit environment: not the
session's PATH, home, git or gpg configuration, credentials or proxy. What
the Node suite could only say with a fake `python3` on PATH is said here
with a fake harvester in the scratch home the daemon resolves its root from.
The cases added to the port's are marked "port:": the signed-action fence
(the Node suite reached it only through the upgrade), the threads' ordering,
and the mutations the first version of these tests left alive.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import zlib
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import agentd, gzcoord, sign  # noqa: E402
from control.ops import memory_slug  # noqa: E402

AGENTD = os.path.join(HERE, "tools", "fabric", "control", "agentd.py")
ME = {"address": "develop-qzapp/db-admin"}
OPERATORS = {"develop-qzapp/user"}
WHO = gzcoord.whoami()
SELF = f"{WHO['host']}/{WHO['agent']}"


def iso(ms: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{int(ms) % 1000:03d}Z"


def now_iso() -> str:
    return iso(time.time() * 1000)


def request_body(**over) -> dict:
    return {"v": 1, "kind": "request", "id": agentd.new_id(), "from": "develop-qzapp/user", "to": "*", "op": "ping",
            "ts": now_iso(), "ttl_s": 30, **over}


def req(**over) -> dict:
    return {"content": json.dumps(request_body(**over))}


def request(**over) -> str:
    return json.dumps(request_body(**over))


class Scratch(unittest.TestCase):
    """Every directory a case makes is removed when it ends, however it ends."""

    def scratch(self, prefix: str = "agentd-") -> str:
        d = tempfile.mkdtemp(prefix=prefix)
        self.addCleanup(shutil.rmtree, d, True)
        return d


class FakeRelay:
    """A channel in memory: /api/messages (newest N, or after since_id),
    /api/wait (after since_id, long-poll to timeout_seconds) and /api/send.
    Records every path, so a test can say what was never called."""

    def __init__(self, initial=()):
        self.rows: list[dict] = []
        self.posts: list[tuple[str, str]] = []   # (channel, the body as sent)
        self.hits: list[str] = []
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.wait_answer = None   # a page /api/wait answers with, whatever the channel holds
        for sender, content in initial:
            self.add(sender, content)
        relay = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _json(self, obj, status=200):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _after(self, since):
                ids = [r["id"] for r in relay.rows]
                return None if since not in ids else relay.rows[ids.index(since) + 1:]

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                with relay.lock:
                    relay.hits.append(u.path + ("?" + u.query if u.query else ""))
                if u.path == "/api/messages":
                    with relay.lock:
                        since, limit = q.get("since_id"), int(q.get("limit") or 50)
                        if since:
                            a = self._after(since)
                            return self._json({"messages": [], "warning": "since_id_not_found"} if a is None else {"messages": a[:limit]})
                        return self._json({"messages": relay.rows[-limit:]})
                if u.path == "/api/wait" and relay.wait_answer is not None:
                    return self._json(relay.wait_answer)
                if u.path == "/api/wait":
                    deadline = time.monotonic() + float(q.get("timeout_seconds") or 1)
                    while not relay.closed.is_set():
                        with relay.lock:
                            a = self._after(q["since_id"]) if q.get("since_id") else list(relay.rows)
                            if a is None:
                                return self._json({"messages": [], "warning": "since_id_not_found"})
                            if a or time.monotonic() >= deadline:
                                return self._json({"messages": a[:50]})
                        time.sleep(0.02)
                    return None
                self._json({}, 404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("content-length") or 0))
                with relay.lock:
                    relay.hits.append(self.path)
                if self.path == "/api/send":
                    j = json.loads(body)
                    with relay.lock:
                        relay.posts.append((j["channel"], body.decode()))
                    r = relay.add(j["sender"], j["content"])
                    return self._json({"seq": r["seq"], "id": r["id"], "deduplicated": False})
                self._json({}, 404)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add(self, sender: str, content: str) -> dict:
        with self.lock:
            n = len(self.rows) + 1 + getattr(self, "_gone", 0)
            r = {"seq": n, "id": f"id-{n}", "sender": sender, "content": content, "timestamp": now_iso()}
            self.rows.append(r)
            return r

    def clear(self) -> None:
        with self.lock:
            self._gone = getattr(self, "_gone", 0) + len(self.rows)
            self.rows.clear()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def waits(self) -> int:
        with self.lock:
            return len([h for h in self.hits if h.startswith("/api/wait?")])

    def until_waiting(self, after: int = 0, timeout: float = 20) -> None:
        end = time.monotonic() + timeout
        while self.waits() <= after:
            if time.monotonic() > end:
                raise AssertionError("the daemon never waited")
            time.sleep(0.02)

    def replies(self) -> list[dict]:
        out = []
        with self.lock:
            for r in self.rows:
                try:
                    j = json.loads(r["content"])
                except ValueError:
                    continue
                if isinstance(j, dict) and j.get("kind") == "reply":
                    out.append(j)
        return out

    def close(self) -> None:
        self.closed.set()
        self.server.shutdown()
        self.server.server_close()


def executable(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, 0o755)


class Daemon(Scratch):
    """The real agentd.py as a subprocess, in an environment this class builds."""

    def setUp(self):
        # The registry the daemon reads is the operator root's (ADR-045): a copy
        # of this checkout's own, so the cases answer the same whatever
        # AGENT_FABRIC_OPERATOR the run had.
        self.operator = self.scratch("agentd-operator-")
        os.makedirs(os.path.join(self.operator, "runtime", "hosts"))
        shutil.copy(os.path.join(HERE, "runtime", "hosts", "registry.json"), os.path.join(self.operator, "runtime", "hosts", "registry.json"))

    def home(self) -> str:
        h = self.scratch("agentd-home-")
        os.makedirs(os.path.join(h, ".config", "agent-fabric"))
        with open(os.path.join(h, ".config", "agent-fabric", "secrets.env"), "w", encoding="utf-8") as fh:
            fh.write("export CLAUDE_BRIDGE_AUTH_TOKEN='tok-fixture'\nexport OPENROUTER_API_KEY='sk-or-secret-value-0123456789'\n")
        return h

    def env(self, url: str, **over) -> dict:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.home(), "AGENT_FABRIC_OPERATOR": self.operator,
               "GIT_CONFIG_NOSYSTEM": "1", "CLAUDE_BRIDGE_URL": url, "FABRIC_CONTROL_CHANNEL": "test:control",
               "GZCOORD_DEFAULT_LOCALE_ONLY": "1"}
        if os.environ.get("TMPDIR"):
            env["TMPDIR"] = os.environ["TMPDIR"]
        env.update(over)
        return {k: v for k, v in env.items() if v is not None}

    def run_once(self, url: str, timeout: float = 60, **over) -> SimpleNamespace:
        """Asynchronous with respect to the fake relay: it lives in this process's threads."""
        p = subprocess.run([sys.executable, AGENTD, "--once"], env=self.env(url, **over), capture_output=True, text=True,
                           timeout=timeout, check=False, stdin=subprocess.DEVNULL)
        return SimpleNamespace(status=p.returncode, stderr=p.stderr, stdout=p.stdout)

    def start(self, url: str, **over) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, AGENTD], env=self.env(url, **over), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(self._stop, p)
        return p

    @staticmethod
    def _stop(p: subprocess.Popen) -> None:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
        try:
            p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()

    def with_relay(self, initial=()) -> FakeRelay:
        r = FakeRelay(initial)
        self.addCleanup(r.close)
        return r

    def once_after_wait(self, r: FakeRelay, posts, **over) -> SimpleNamespace:
        """--once primes, then waits: the posts land after the first wait, which is what it sees."""
        def later():
            try:
                r.until_waiting()
                for sender, content in posts:
                    r.add(sender, content)
            except AssertionError:
                pass
        t = threading.Thread(target=later, daemon=True)
        t.start()
        out = self.run_once(r.url(), **over)
        t.join(5)
        return out


class Accept(unittest.TestCase):
    def test_accept_the_fence_case_by_case(self):
        seen = agentd.Seen()
        kw = dict(me=ME, operators=OPERATORS, ttl_s=30, seen=seen)
        ok = agentd.accept(req(), **kw)
        self.assertTrue(ok["ok"], ok)
        self.assertTrue(agentd.accept(req(to="develop-qzapp/db-admin"), **kw)["ok"], "addressed to me")
        self.assertTrue(agentd.accept(req(to=["develop-qzapp/x", "develop-qzapp/db-admin"]), **kw)["ok"], "in a list")
        self.assertEqual(agentd.accept(req(to="develop-qzapp/other"), **kw)["why"], "not for me")
        self.assertRegex(agentd.accept(req(op="shutdown"), **kw)["why"], r"^op shutdown")
        self.assertRegex(agentd.accept(req(**{"from": "develop-qzapp/backend-dev-01"}), **kw)["why"], r"not an operator$")
        # presence is answered for any placed account; every other op still only for an operator
        accounts = {"develop-qzapp/backend-dev-01", "develop-qzapp/db-admin"}
        kwa = dict(kw, accounts=accounts)
        self.assertTrue(agentd.accept(req(**{"from": "develop-qzapp/backend-dev-01", "op": "presence"}), **kwa)["ok"], "a placed account may ask presence")
        self.assertRegex(agentd.accept(req(**{"from": "develop-qzapp/backend-dev-01", "op": "session"}), **kwa)["why"], r"not an operator$", "but nothing else")
        self.assertRegex(agentd.accept(req(**{"from": "elsewhere/stranger", "op": "presence"}), **kwa)["why"], r"not an operator or a placed account",
                         "an address no host places is refused")
        self.assertEqual(agentd.accept(req(ts=iso(time.time() * 1000 - 60000), ttl_s=30), **kw)["why"], "expired")
        self.assertEqual(agentd.accept(req(ts="garbage"), **kw)["why"], "expired")
        self.assertEqual(agentd.accept({"content": "not json"}, **kw)["why"], "not json")
        self.assertEqual(agentd.accept({"content": json.dumps({"v": 1, "kind": "reply", "id": "x"})}, **kw)["why"], "not a request")
        self.assertEqual(agentd.accept(req(v=2), **kw)["why"], "v 2")
        dup = req()
        rid = json.loads(dup["content"])["id"]
        self.assertTrue(agentd.accept(dup, **kw)["ok"])
        agentd.remember(seen, rid)
        self.assertEqual(agentd.accept(dup, **kw)["why"], "seen")
        for i in range(agentd.SEEN_MAX + 5):
            agentd.remember(seen, f"x{i}")
        self.assertLessEqual(len(seen), agentd.SEEN_MAX + 1, "the LRU is bounded")
        self.assertNotIn(rid, seen, "the oldest ids fall out")

    def test_port_the_checks_the_node_suite_left_to_its_neighbours(self):
        kw = dict(me=ME, operators=OPERATORS, ttl_s=30, seen=agentd.Seen())
        self.assertEqual(agentd.accept({}, **kw)["why"], "not json", "a record with no content")
        self.assertEqual(agentd.accept({"content": "[1]"}, **kw)["why"], "not a request", "JSON that is no object")
        self.assertEqual(agentd.accept(req(v=True), **kw)["why"], "v true", "true is not the number 1")
        self.assertEqual(agentd.accept(req(v=1.0), **kw)["ok"], True, "1.0 is the number 1, as JSON.parse reads it")
        self.assertEqual(agentd.accept(req(id=""), **kw)["why"], "no id")
        self.assertEqual(agentd.accept(req(id=7), **kw)["why"], "no id")
        self.assertEqual(agentd.accept(req(op="x" * 30), **kw)["why"], "op " + "x" * 20, "the op is cut at 20 for the log")
        self.assertRegex(agentd.accept(req(**{"from": "f" * 60}), **kw)["why"], r"^from f{40} is not an operator$")
        self.assertRegex(agentd.accept(req(**{"from": None}), **kw)["why"], r"^from null is not an operator$")
        # ttl: the request's own, capped at an hour for a read; the config's when it names none
        old = iso(time.time() * 1000 - 120000)
        self.assertEqual(agentd.accept(req(ts=old, ttl_s=60), **kw)["why"], "expired")
        self.assertTrue(agentd.accept(req(ts=old, ttl_s=300), **kw)["ok"])
        self.assertEqual(agentd.accept(req(ts=old, ttl_s=0), **kw)["why"], "expired", "no ttl of its own: the config's 30 s")
        self.assertEqual(agentd.accept(req(ts=iso(time.time() * 1000 - 7200000), ttl_s=10 ** 9), **kw)["why"], "expired", "an hour at most")

    def test_port_an_action_needs_the_operators_signature_a_fresh_ts_and_a_newer_one_than_the_last(self):
        key = sign.generate_operator_key()
        pub = sign.public_key_from(key["publicKeySpec"])
        kw = dict(me=ME, operators=OPERATORS, ttl_s=30, seen=agentd.Seen(), keys={"develop-qzapp/user": pub})

        def action(**over):
            body = request_body(**{"op": "upgrade", "args": {"piece": "claude"}, "ttl_s": 60, **over})
            return {"content": json.dumps(sign.sign_request(body, key["privateKeySpec"]))}
        good = agentd.accept(action(), **kw)
        self.assertTrue(good["ok"], good)
        self.assertRegex(agentd.accept(req(op="upgrade", args={"piece": "claude"}), **kw)["why"], r"^upgrade: not signed by develop-qzapp/user's key$")
        self.assertRegex(agentd.accept(action(), **{**kw, "keys": {}})["why"], r"not signed by", "an operator with no key orders nothing")
        forged = json.loads(action()["content"])
        forged["args"] = {"piece": "fabric"}
        self.assertRegex(agentd.accept({"content": json.dumps(forged)}, **kw)["why"], r"not signed by", "a signed request altered")
        future = agentd.accept(action(ts=iso(time.time() * 1000 + 120000)), **kw)
        self.assertRegex(future["why"], r"^upgrade: dated (119|120) s in the future \(the operator's clock\?\)$")
        self.assertTrue(agentd.accept(action(ts=iso(time.time() * 1000 + 30000)), **kw)["ok"], "inside the minute's skew")
        old = agentd.accept(action(ts=iso(time.time() * 1000 - 30000)), **{**kw, "action_floor": lambda _f: time.time() * 1000 - 10000})
        self.assertRegex(old["why"], r"^upgrade: not newer than the last action accepted from develop-qzapp/user \(a replay\)$")
        at = iso(time.time() * 1000 - 1000)
        ts = agentd.accept(action(ts=at), **kw)["ts"]
        self.assertFalse(agentd.accept(action(ts=at), **{**kw, "action_floor": lambda _f: ts})["ok"], "equal is a replay")
        self.assertTrue(agentd.accept(action(ts=at), **{**kw, "action_floor": lambda _f: ts - 1})["ok"], "strictly newer is not")
        # an action lives ten minutes at most, whatever it asks
        self.assertEqual(agentd.accept(action(ts=iso(time.time() * 1000 - 700000), ttl_s=100000), **kw)["why"], "expired")
        self.assertTrue(agentd.accept(action(ts=iso(time.time() * 1000 - 500000), ttl_s=100000), **kw)["ok"])


def gzcoord_ts(text: str) -> int:
    from control.sessions import date_parse
    return int(date_parse(text))


class Pieces(Scratch):
    def test_operator_addresses_and_control_config_read_the_fabrics_own_files(self):
        ops = agentd.operator_addresses(os.path.join(HERE, "runtime", "hosts", "registry.json"))
        self.assertIn("develop-qzapp/user", ops)
        self.assertEqual(agentd.operator_addresses("/nonexistent"), set())
        c = agentd.control_config({})
        self.assertEqual((c["channel"], c["ttl_s"]), ("fabric:control", 30))
        self.assertEqual(agentd.control_config({"FABRIC_CONTROL_CHANNEL": "x:control", "CLAUDE_BRIDGE_URL": "http://h:1"})["relay_url"], "http://h:1")

    def test_port_the_registry_gives_operators_in_its_order_and_keys_only_to_a_wellformed_host(self):
        key = sign.generate_operator_key()
        reg = os.path.join(self.scratch(), "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"b": {"operator": "boss", "operator_key": key["publicKeySpec"]}, "a": {}, "c": {"operator_key": "junk"}},
                       "placement": {"x": "a", "y": "b"}}, fh)
        self.assertEqual(agentd.operator_list(reg), ["b/boss", "a/user", "c/user"])
        self.assertEqual(agentd.account_addresses(reg), {"a/x", "b/y"})
        self.assertEqual(agentd.operator_keys(reg), {"b/boss": sign.public_key_from(key["publicKeySpec"])})
        self.assertEqual(agentd.operator_keys("/nonexistent"), {})

    def test_port_the_registry_keys_keep_those_read_before_a_null_host_and_skip_a_key_openssl_cannot_read(self):
        key = sign.generate_operator_key()
        reg = os.path.join(self.scratch(), "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            fh.write('{"hosts": {"b": {"operator": "boss", "operator_key": %s}, "n": null, "c": {"operator_key": %s}}}'
                     % (json.dumps(key["publicKeySpec"]), json.dumps(key["publicKeySpec"])))
        self.assertEqual(list(agentd.operator_keys(reg)), ["b/boss"], "the Node's partial map: what was read before the null")
        from unittest import mock
        with mock.patch.object(agentd, "public_key_from", side_effect=sign.SignError("openssl missing")):
            self.assertEqual(agentd.operator_keys(reg), {}, "a key openssl cannot parse is no key, never an error that stops the reads")

    def test_port_keys_are_parsed_only_for_an_action_that_passed_the_sender_check(self):
        calls = []

        def keys():
            calls.append(1)
            return {}
        kw = dict(me=ME, operators=OPERATORS, ttl_s=30, seen=agentd.Seen(), keys=keys)
        agentd.accept(req(), **kw)
        agentd.accept({"content": "junk"}, **kw)
        agentd.accept(req(**{"from": "nobody/x", "op": "upgrade"}), **kw)
        self.assertEqual(calls, [], "no openssl for a read, junk or a stranger")
        agentd.accept(req(op="upgrade", args={"piece": "claude"}), **kw)
        self.assertEqual(calls, [1])

    def test_port_the_ledger_remembers_the_newest_per_sender_privately_and_leaves_no_temporary_file(self):
        d = self.scratch()
        f = os.path.join(d, "state", "actions-seen.json")
        ledger = agentd.action_ledger(f)
        self.assertEqual(ledger.floor("h/user"), 0)
        ledger.record("h/user", 1791461100000.0)
        ledger.record("h/other", 5.0)
        ledger.record("h/user", 1791461000000.0)   # older: not recorded
        self.assertEqual(ledger.floor("h/user"), 1791461100000)
        self.assertEqual(json.load(open(f)), {"h/user": 1791461100000, "h/other": 5})
        self.assertEqual(open(f).read(), '{"h/user":1791461100000,"h/other":5}\n')
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)
        self.assertEqual(os.listdir(os.path.dirname(f)), ["actions-seen.json"])
        for text in ("{broken", "[1]", "null", '{"h/user": "soon"}'):
            open(f, "w").write(text)
            self.assertEqual(ledger.floor("h/user"), 0, text)
        os.unlink(f)
        os.makedirs(f)   # a directory where the file goes: the write fails, and says so
        with self.assertRaises(OSError):
            ledger.record("h/user", 1.0)
        self.assertEqual(os.listdir(os.path.dirname(f)), ["actions-seen.json"], "a failed write leaves no temporary file")

    def test_watch_source_a_changed_source_in_the_watched_files_fires_once_after_the_quiet_period_a_txt_does_not(self):
        d = self.scratch("agentd-src-")
        fired = []

        def files():
            return [os.path.join(d, n) for n in os.listdir(d) if n.endswith((".py", ".json"))]
        w = agentd.watch_source(lambda: fired.append(time.monotonic()), files, poll_s=0.05, quiet_s=0.4, new_is_change=True)
        self.addCleanup(w.stop)
        open(os.path.join(d, "notes.txt"), "w").write("x")
        time.sleep(0.8)
        self.assertEqual(fired, [], "a non-source file is not a change")
        t0 = time.monotonic()
        open(os.path.join(d, "a.py"), "w").write("1")   # a pull: several files
        open(os.path.join(d, "b.py"), "w").write("2")
        time.sleep(1.2)
        self.assertEqual(len(fired), 1, "one restart for one pull")
        self.assertGreaterEqual(fired[0] - t0, 0.4, "after the quiet period, not at the first write")
        os.unlink(os.path.join(d, "a.py"))
        time.sleep(1.2)
        self.assertEqual(len(fired), 2, "a source that goes away is a change too")

    def test_port_a_file_first_seen_is_a_baseline_where_the_set_grows_by_itself_a_change_where_it_does_not(self):
        # loaded_sources() grows as the daemon imports a module late; that is not a pull.
        d = self.scratch("agentd-grow-")
        names = [os.path.join(d, "a.py")]
        open(names[0], "w").write("1")
        fired = []
        w = agentd.watch_source(lambda: fired.append(1), lambda: list(names), poll_s=0.05, quiet_s=0.2)
        self.addCleanup(w.stop)
        open(os.path.join(d, "b.py"), "w").write("2")
        names.append(os.path.join(d, "b.py"))
        time.sleep(0.6)
        self.assertEqual(fired, [], "a module imported late is not a change")
        open(os.path.join(d, "b.py"), "w").write("22")
        time.sleep(0.6)
        self.assertEqual(len(fired), 1, "but once seen, its change is")

    def test_port_the_files_watched_are_the_loaded_modules_and_the_config_and_nothing_else_of_the_tree(self):
        files = agentd.loaded_sources()
        self.assertIn(agentd.CONFIG, files)
        self.assertIn(os.path.realpath(agentd.__file__) if os.path.realpath(agentd.__file__) in files else agentd.__file__, files)
        self.assertTrue(all(f == agentd.CONFIG or f.endswith(".py") for f in files))
        self.assertFalse(any(f.endswith(".mjs") for f in files), "a Node module is not the Python daemon's code")
        self.assertEqual(agentd.QUIET_S, 2)

    def test_accounts_keeper_the_timer_and_a_request_share_one_reading_the_cache_answers_inside_its_window_a_failed_read_does_not_jam_the_next(self):
        clock, reads = [0], [0]
        gate, entered = threading.Event(), threading.Event()
        fail = [False]

        def read():
            reads[0] += 1
            if fail[0]:
                raise RuntimeError("harness gone")
            entered.set()
            gate.wait(10)
            return {"status": "ok", "n": reads[0]}
        k = agentd.accounts_keeper(read, now=lambda: clock[0], cache_ms=1000)
        out = {}
        a = threading.Thread(target=lambda: out.__setitem__("a", k.refresh()))
        b = threading.Thread(target=lambda: out.__setitem__("b", k.cached()))
        a.start()
        entered.wait(10)
        b.start()
        time.sleep(0.1)
        gate.set()
        a.join(10)
        b.join(10)
        self.assertEqual(reads[0], 1, "a timer tick and a request arriving together start one harness run")
        self.assertIs(out["a"], out["b"])
        clock[0] = 500
        self.assertEqual(k.cached()["n"], 1, "inside the window: the last reading, no new run")
        self.assertEqual(reads[0], 1)
        clock[0] = 1500
        self.assertEqual(k.cached()["n"], 2, "past the window: a new reading")
        fail[0] = True
        with self.assertRaisesRegex(RuntimeError, "harness gone"):
            k.refresh()
        fail[0] = False
        self.assertEqual(k.refresh()["n"], 4, "the failed run released the slot")
        self.assertLess(agentd.ACCOUNTS_KEEPALIVE_MS, 8 * 3600 * 1000 / 1.5, "the keeper reads well inside the 8-hour sign-in")

    def test_port_a_failed_reading_reaches_every_caller_that_joined_it(self):
        gate, entered = threading.Event(), threading.Event()

        def read():
            entered.set()
            gate.wait(10)
            raise RuntimeError("boom")
        k = agentd.accounts_keeper(read)
        got = []

        def ask():
            try:
                k.refresh()
            except RuntimeError as e:
                got.append(str(e))
        ts = [threading.Thread(target=ask) for _ in range(3)]
        ts[0].start()
        entered.wait(10)
        ts[1].start()
        ts[2].start()
        time.sleep(0.1)
        gate.set()
        for t in ts:
            t.join(10)
        self.assertEqual(got, ["boom"] * 3)

    def test_leaving_for_new_code_waits_for_every_running_action_to_reply_then_exits_once(self):
        inflight = {"a", "b"}
        exits, logs = [], []
        lv = agentd.leaver(inflight, exit=exits.append, log=logs.append)
        self.assertFalse(lv.settle(), "nothing asked to leave: an action finishing never exits")
        self.assertFalse(lv.request("source changed"))
        self.assertEqual(exits, [], "two actions still running: not yet")
        inflight.discard("a")
        self.assertFalse(lv.settle())
        self.assertEqual(exits, [])
        self.assertFalse(lv.request("the fabric moved (upgrade fabric)"))
        inflight.discard("b")
        self.assertTrue(lv.settle())
        self.assertEqual(exits, [0])
        self.assertRegex(logs[0], r"agentd: source changed; exiting", "the first reason is the one said")
        idle = agentd.leaver(set(), exit=exits.append, log=lambda _m: None)
        self.assertTrue(idle.request("source changed"), "nothing running: leaves at once, as at the base")

    def test_port_the_default_exit_ends_the_process_not_the_thread(self):
        p = subprocess.run([sys.executable, "-c",
                            "import sys, threading; sys.path.insert(0, %r)\n"
                            "from control import agentd\n"
                            "l = agentd.leaver(set(), log=lambda m: None)\n"
                            "t = threading.Thread(target=lambda: l.request('x')); t.start(); t.join()\n"
                            "print('still here')" % os.path.join(HERE, "tools", "fabric")],
                           capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)

    def test_port_up_record_and_state_poster_ride_their_own_channels(self):
        up = agentd.up_record("h/a")
        self.assertEqual(list(up), ["v", "kind", "from", "ts"])
        self.assertEqual((up["v"], up["kind"], up["from"]), (1, "up", "h/a"))
        sent = []
        agentd.state_poster(lambda p, **kw: sent.append((p, kw)), {"state_channel": "s:state:control"}, "h/a")({"k": 1})
        (path, kw), = sent
        self.assertEqual(path, "/api/send")
        self.assertEqual(kw["method"], "POST")
        self.assertEqual(json.loads(kw["body"]), {"channel": "s:state:control", "sender": "h/a", "content": '{"k":1}'})


class Answer(Scratch):
    def test_answer_a_memory_reply_is_the_report_first_then_one_record_per_part_in_order_the_parts_never_ride_in_the_first_record(self):
        tar = os.urandom(2500)
        report = {"claims": 1, "counts": {"in_scope": 1, "total": 1}, "needs_rendering": [], "skipped_no_roles_class": []}
        run = lambda *_a, **_k: SimpleNamespace(stdout=tar, stderr=json.dumps(report).encode())  # noqa: E731
        h = self.scratch("agentd-mem-")
        wc = os.path.join(h, "projects", "gzapp")
        os.makedirs(wc)
        # The slug is the op's own rule (every non-alphanumeric to '-'), not a
        # '/'-only substitution: the run's TMPDIR carries a '.', and the two
        # rules differed exactly there.
        mem = os.path.join(h, ".claude", "projects", memory_slug(wc), "memory")
        os.makedirs(mem)
        open(os.path.join(mem, "a.md"), "w").write("x")
        ctx = {"me": {"address": "h/db-admin"}, "started": now_iso(), "home": h, "run_bounded": run}
        r = agentd.answer({"id": "q1", "op": "memory"}, ctx)
        self.assertEqual((r["op"], r["in_reply_to"], r["data"]["parts"]), ("memory", "q1", 1))
        b = r["data"]["memory"]["bundles"][0]
        self.assertEqual((b["status"], b["parts"], b["working_copy"], b["report"]["claims"]), ("ok", 1, wc, 1))
        self.assertNotIn("_parts", b)
        self.assertNotIn("chunk", json.dumps(r["data"]), "the first record carries the report and sizes, not the bundle")
        self.assertEqual(len(r["_followups"]), 1)
        f = r["_followups"][0]
        self.assertEqual((f["kind"], f["in_reply_to"], f["from"]), ("reply", "q1", "h/db-admin"))
        self.assertNotEqual(f["id"], r["id"])
        self.assertEqual(list(f["data"]), ["part"])
        self.assertEqual({k: f["data"]["part"][k] for k in ("slug", "part", "parts")}, {"slug": b["slug"], "part": 1, "parts": 1})
        self.assertEqual(zlib.decompress(base64.b64decode(f["data"]["part"]["chunk"]), 47), tar)
        self.assertEqual(hashlib.sha256(tar).hexdigest(), b["sha256"])
        ping = agentd.answer({"id": "q2", "op": "ping"}, ctx)
        self.assertNotIn("_followups", ping, "only a memory reply has follow-ups")
        empty = agentd.answer({"id": "q3", "op": "memory"}, {**ctx, "home": self.scratch("agentd-nomem-")})
        self.assertEqual(empty["data"]["memory"], {"status": "ok", "bundles": []})
        self.assertEqual((empty["data"]["parts"], empty["_followups"]), (0, []))
        # A tokens request names its window; unset, absurd or huge, the op's default or the 90-day cap decides.
        tk = agentd.answer({"id": "q4", "op": "tokens", "days": 3}, ctx)
        self.assertEqual(tk["data"]["tokens"]["days"], 3)
        self.assertIn("identity", tk["data"], "tokens rides with identity")
        self.assertEqual(agentd.answer({"id": "q5", "op": "tokens"}, ctx)["data"]["tokens"]["days"], 7)
        self.assertEqual(agentd.answer({"id": "q6", "op": "tokens", "days": -2}, ctx)["data"]["tokens"]["days"], 7)
        self.assertEqual(agentd.answer({"id": "q7", "op": "tokens", "days": 9999}, ctx)["data"]["tokens"]["days"], 90)

    def test_port_a_reply_is_one_record_in_the_wires_key_order_with_the_daemons_own_meta(self):
        ctx = {"me": {"address": "h/a"}, "started": iso(time.time() * 1000 - 5000)}
        r = agentd.answer({"id": "q", "op": "ping"}, ctx)
        self.assertEqual(list(r), ["v", "kind", "id", "in_reply_to", "from", "op", "ts", "ok", "data"])
        self.assertEqual(list(r["data"]), ["agentd"])
        self.assertEqual(list(r["data"]["agentd"]), ["pid", "started", "uptime_s"])
        self.assertEqual(r["data"]["agentd"]["pid"], os.getpid())
        self.assertIn(r["data"]["agentd"]["uptime_s"], (5, 6))
        self.assertIs(r["ok"], True)

    def test_port_an_action_refused_by_its_module_is_still_a_reply_with_the_modules_words(self):
        ctx = {"me": {"address": "h/a"}, "started": now_iso(), "home": self.scratch(), "root": self.scratch()}
        for op in ("local-prune", "tools-install", "pool-add", "pool-list", "pool-claim", "jobs-add"):
            r = agentd.answer({"id": "q", "op": op, "to": "*", "args": {"zz": 1}, "from": "h/user"}, ctx)
            self.assertEqual((r["op"], list(r["data"])[0]), (op, op))
            self.assertEqual(r["data"][op]["status"], "refused", (op, r["data"][op]))


class Wire(Daemon):
    def test_once_primes_from_the_newest_record_answers_a_live_request_never_acks_never_answers_history(self):
        r = self.with_relay([("develop-qzapp/user", request(op="status"))])   # history: must not be answered
        out = self.once_after_wait(r, [("develop-qzapp/user", request(op="ping"))])
        self.assertEqual(out.status, 0, out.stderr)
        rs = r.replies()
        self.assertEqual(len(rs), 1, f"replies: {rs}\n{out.stderr}")
        self.assertEqual((rs[0]["op"], rs[0]["ok"]), ("ping", True))
        self.assertGreater(rs[0]["data"]["agentd"]["pid"], 0)
        self.assertNotEqual(rs[0]["in_reply_to"], json.loads(r.rows[0]["content"])["id"], "the historical status request was not answered")
        self.assertFalse([h for h in r.hits if h.startswith("/api/ack")], "no ack ever")
        self.assertTrue([h for h in r.hits if h.startswith("/api/messages?") and "limit=1" in h], "primed from the newest record")
        self.assertTrue([h for h in r.hits if h.startswith("/api/wait?") and "since_id=id-1" in h], "waited after it")
        self.assertRegex(out.stderr, r"agentd: answered ping for develop-qzapp/user \([0-9a-f]{8}\)")
        self.assertRegex(out.stderr, r"agentd: develop-qzapp/\S+ on test:control at http://127\.0\.0\.1:\d+; operators: .*develop-qzapp/user")

    def test_once_a_request_from_a_non_operator_an_unknown_op_and_an_expired_one_get_no_reply_keys_carry_no_value(self):
        r = self.with_relay([("develop-qzapp/user", request(op="ping", id="primer"))])
        out = self.once_after_wait(r, [
            ("develop-qzapp/backend-dev-01", request(op="ping", **{"from": "develop-qzapp/backend-dev-01"})),
            ("develop-qzapp/user", request(op="rm -rf")),
            ("develop-qzapp/user", request(op="ping", ts=iso(time.time() * 1000 - 3600000))),
            ("develop-qzapp/user", request(op="keys", to="develop-qzapp/nobody")),
            ("develop-qzapp/user", request(op="keys"))])
        self.assertEqual(out.status, 0, out.stderr)
        rs = r.replies()
        self.assertEqual(len(rs), 1, rs)
        self.assertEqual(rs[0]["op"], "keys")
        self.assertIn('agentd: ignored a record "from develop-qzapp/backend-dev-01 is not an operator"', out.stderr)
        self.assertIn('agentd: ignored a record "op rm -rf"', out.stderr)
        self.assertIn('agentd: ignored a record "expired"', out.stderr)
        self.assertNotRegex(out.stderr, r"not for me|not a request", "the quiet refusals stay quiet")
        k = next(x for x in rs[0]["data"]["keys"] if x["name"] == "OPENROUTER_API_KEY")
        self.assertIs(k["present"], True)
        self.assertEqual(len(k["sha256_12"]), 12)
        self.assertNotIn("sk-or-secret-value", json.dumps(rs), "no key value in a reply")

    def test_once_the_keys_probe_reads_the_scratch_home_never_the_runners_git_config_or_keyring(self):
        # The keys probe asks git for the signing key and gpg for its secret.
        # The runner's GIT_CONFIG_GLOBAL, XDG_CONFIG_HOME and GNUPGHOME are set
        # hostile here; a gpg that records how it was asked sits first on
        # PATH. The positive control: the scratch HOME's own ~/.gitconfig
        # naming a key does reach that gpg, with no GNUPGHOME, so silence in
        # the first run is the environment kept out, not a recorder never
        # reached.
        hostile = self.scratch("agentd-hostile-")
        open(os.path.join(hostile, "gitconfig"), "w").write("[user]\n\tsigningkey = HOSTILEKEY\n")
        os.makedirs(os.path.join(hostile, "xdg", "git"))
        open(os.path.join(hostile, "xdg", "git", "config"), "w").write("[user]\n\tsigningkey = HOSTILEKEY\n")
        bin_ = self.scratch("agentd-gpg-")
        asked = os.path.join(bin_, "asked")
        executable(os.path.join(bin_, "gpg"), f'#!/bin/sh\necho "GNUPGHOME=${{GNUPGHOME-unset}} $*" >> "{asked}"\nexit 2\n')
        path = f"{bin_}:{os.environ.get('PATH', '/usr/bin:/bin')}"
        # The runner has them; the daemon is started in an environment built
        # from nothing (Daemon.env), so it never sees them. The positive
        # control below is what shows the recorder is reachable.
        saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "XDG_CONFIG_HOME", "GNUPGHOME")}
        os.environ.update({"GIT_CONFIG_GLOBAL": os.path.join(hostile, "gitconfig"), "XDG_CONFIG_HOME": os.path.join(hostile, "xdg"), "GNUPGHOME": hostile})
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])

        def keys_once(home=None):
            r = self.with_relay([("develop-qzapp/user", request(op="ping", id="primer"))])
            over = {"PATH": path, **({"HOME": home} if home else {})}
            out = self.once_after_wait(r, [("develop-qzapp/user", request(op="keys"))], **over)
            self.assertEqual(out.status, 0, out.stderr)
            self.assertEqual(len(r.replies()), 1, out.stderr)
            return r.replies()[0]
        reply = keys_once()
        self.assertEqual(next(k for k in reply["data"]["keys"] if k["name"] == agentd.ops.SIGNING_ROW), {"name": agentd.ops.SIGNING_ROW, "present": False})
        self.assertFalse(os.path.exists(asked), "gpg was asked under the runner's config")
        home = self.home()
        open(os.path.join(home, ".gitconfig"), "w").write("[user]\n\tsigningkey = SCRATCHKEY\n")
        keys_once(home)
        with open(asked) as fh:
            self.assertEqual(fh.read(), "GNUPGHOME=unset --list-secret-keys --with-colons -- SCRATCHKEY\n")

    def test_once_a_slow_disk_answers_beside_the_loop_a_ping_sent_after_it_is_answered_first(self):
        bin_ = self.scratch("agentd-du-")
        executable(os.path.join(bin_, "du"), '#!/bin/sh\nsleep 3\nfor a in "$@"; do case "$a" in -*) ;; *) printf "7\\t%s\\0" "$a";; esac; done\n')
        r = self.with_relay([("develop-qzapp/user", request(op="ping", id="primer"))])
        out = self.once_after_wait(r, [("develop-qzapp/user", request(op="disk")), ("develop-qzapp/user", request(op="ping"))],
                                   PATH=f"{bin_}:{os.environ.get('PATH', '/usr/bin:/bin')}")
        self.assertEqual(out.status, 0, out.stderr)
        rs = r.replies()
        self.assertEqual([x["op"] for x in rs], ["ping", "disk"], f"the ping was not held behind the disk:\n{out.stderr}")
        self.assertIs(rs[1]["ok"], True)
        self.assertGreater(rs[1]["data"]["disk"]["total_kb"], 0)
        self.assertIsInstance(rs[1]["data"]["disk"]["largest"], list)

    def test_once_three_disk_requests_share_one_scan_and_each_is_answered(self):
        # Review of #92, round 4: one scan per daemon, shared by every request
        # that arrives while it runs — any placed account may post the read unsigned.
        bin_ = self.scratch("agentd-du-")
        count = os.path.join(bin_, "calls")
        executable(os.path.join(bin_, "du"), f'#!/bin/sh\necho x >> {json.dumps(count)}\nsleep 2\n'
                   'for a in "$@"; do case "$a" in -*) ;; *) printf "7\\t%s\\0" "$a";; esac; done\n')
        r = self.with_relay([("develop-qzapp/user", request(op="ping", id="primer"))])
        out = self.once_after_wait(r, [("develop-qzapp/user", request(op="disk")) for _ in range(3)],
                                   PATH=f"{bin_}:{os.environ.get('PATH', '/usr/bin:/bin')}")
        self.assertEqual(out.status, 0, out.stderr)
        rs = [x for x in r.replies() if x["op"] == "disk"]
        self.assertEqual(len(rs), 3, f"every request answered:\n{out.stderr}")
        self.assertTrue(all(x["ok"] and x["data"]["disk"]["total_kb"] > 0 for x in rs), [x["data"] for x in rs])
        with open(count) as fh:
            calls = len(fh.read().strip().split("\n"))
        self.assertLessEqual(calls, 2, f"one scan (at most two du: the entries and projects/), not one per request: {calls}")

    def test_once_an_empty_channel_is_primed_with_an_up_record_a_cleared_history_reprimes_instead_of_spinning(self):
        r = self.with_relay()
        # The relay's history is cleared while the daemon waits: the wait comes
        # back with the warning, the daemon primes again (a second limit=1
        # read, a second up record) and waits after the new id.
        threading.Thread(target=lambda: (r.until_waiting(), r.clear()), daemon=True).start()
        out = self.run_once(r.url())
        self.assertEqual(out.status, 0, out.stderr)
        self.assertEqual(len(r.rows), 1, r.rows)
        up = json.loads(r.rows[0]["content"])
        self.assertEqual(up["kind"], "up")
        self.assertEqual(up["from"], SELF)
        primes = [h for h in r.hits if h.startswith("/api/messages?") and "limit=1" in h]
        self.assertEqual(len(primes), 2, f"primed once at start and once after the warning: {r.hits}")
        waits = [h for h in r.hits if h.startswith("/api/wait?")]
        self.assertTrue(2 <= len(waits) <= 3, f"one wait per prime, no spin: {waits}")
        self.assertIn(f"since_id={r.rows[0]['id']}", waits[-1], "the last wait follows the new up record")

    def test_once_a_memory_request_is_answered_with_the_report_then_the_bundle_in_parts_under_the_relays_limit(self):
        payload = os.urandom(200 * 1024)   # ~267 KB of base64: three parts at 90 KiB
        home = self.home()
        wc = os.path.join(home, "projects", "gzapp")
        os.makedirs(wc)
        mem = os.path.join(home, ".claude", "projects", memory_slug(wc), "memory")
        os.makedirs(mem)
        open(os.path.join(mem, "a.md"), "w").write("x")
        # The daemon resolves its root from the home when AGENT_FABRIC_ROOT is
        # unset: a harvester there that answers with a fixed payload on stdout
        # and the report on stderr, bigger than one relay message.
        fab = os.path.join(home, "projects", "agent-fabric", "tools", "fabric")
        os.makedirs(fab)
        open(os.path.join(fab, "payload.tar"), "wb").write(payload)
        open(os.path.join(fab, "harvest_memory.py"), "w").write(
            "import os, sys\nsys.stdout.buffer.write(open(os.path.join(os.path.dirname(__file__), 'payload.tar'), 'rb').read())\n"
            "sys.stderr.write('{\"claims\": 4, \"counts\": {\"in_scope\": 5, \"total\": 5}, \"needs_rendering\": [\"ka-1\"], \"skipped_no_roles_class\": []}')\n")
        r = self.with_relay([("develop-qzapp/user", request(op="ping", id="primer"))])
        out = self.once_after_wait(r, [("develop-qzapp/user", request(op="memory"))], HOME=home)
        self.assertEqual(out.status, 0, out.stderr)
        rs = r.replies()
        self.assertEqual(len(rs), 4, f"one report record and three parts: {[list(x['data']) for x in rs]}\n{out.stderr}")
        first, parts = rs[0], rs[1:]
        self.assertEqual((first["data"]["parts"], len(first["data"]["memory"]["bundles"])), (3, 1))
        b = first["data"]["memory"]["bundles"][0]
        self.assertEqual((b["status"], b["parts"], b["bytes"], b["working_copy"]), ("ok", 3, len(payload), wc))
        self.assertEqual(b["report"], {"claims": 4, "counts": {"in_scope": 5, "total": 5}, "needs_rendering": ["ka-1"], "skipped_no_roles_class": []})
        self.assertEqual([p["data"]["part"]["part"] for p in parts], [1, 2, 3], "in order")
        self.assertTrue(all(p["data"]["part"]["parts"] == 3 and p["data"]["part"]["slug"] == b["slug"] and p["in_reply_to"] == first["in_reply_to"] for p in parts))
        for row in r.rows:
            self.assertLess(len(row["content"]), 128 * 1024, "every record under the relay's limit")
        tar = zlib.decompress(base64.b64decode("".join(p["data"]["part"]["chunk"] for p in parts)), 47)
        self.assertEqual(tar, payload)
        self.assertEqual(hashlib.sha256(tar).hexdigest(), b["sha256"])

    def test_a_registry_with_no_operator_is_a_refusal_to_start_not_a_silent_daemon(self):
        r = self.with_relay()
        out = self.run_once(r.url(), AGENT_FABRIC_HOSTS_REGISTRY="/nonexistent/registry.json")
        self.assertEqual(out.status, 3, out.stderr)
        self.assertIn("no host operator", out.stderr)
        self.assertEqual(r.hits, [], "the relay was never contacted")

    def test_port_no_token_is_a_refusal_to_start_too(self):
        r = self.with_relay()
        home = self.scratch("agentd-notoken-")
        out = self.run_once(r.url(), HOME=home)
        self.assertEqual(out.status, 3, out.stderr)
        self.assertIn("no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)", out.stderr)
        self.assertEqual(r.hits, [])

    def test_once_a_refused_token_is_reread_from_the_synced_file_once_then_reported(self):
        hits: list = []

        class Refuse(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):
                hits.append(self.headers.get("authorization"))
                self.send_response(401)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Refuse)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        out = self.run_once(f"http://127.0.0.1:{server.server_address[1]}", CLAUDE_BRIDGE_AUTH_TOKEN="tok-stale")
        self.assertEqual(out.status, 4, out.stderr)
        self.assertIn("agentd: the relay refused this token (HTTP 401); rotated? run fabric-secrets sync", out.stderr)
        self.assertIn("Bearer tok-fixture", hits, f"the synced value was tried: {hits}")

    def test_port_a_relay_that_is_down_is_exit_1_once_and_said_once(self):
        s = tempfile_port()
        out = self.run_once(f"http://127.0.0.1:{s}")
        self.assertEqual(out.status, 1, out.stderr)
        self.assertRegex(out.stderr, rf"agentd: relay unreachable at http://127\.0\.0\.1:{s} \(.*\) — retrying every 30 s\n$")

    def test_port_a_relay_page_that_is_no_array_is_a_failed_read_as_in_the_node(self):
        for page in ({"messages": {}}, ["x"], {"messages": "abc"}):
            r = self.with_relay([(SELF, request(op="ping", id="primer"))])
            r.wait_answer = page
            out = self.run_once(r.url())
            self.assertEqual(out.status, 1, (page, out.stderr))
            self.assertIn("agentd: relay unreachable at", out.stderr)

    def test_port_self_prints_the_status_without_a_relay(self):
        p = subprocess.run([sys.executable, AGENTD, "--self"], env=self.env("http://127.0.0.1:9"), capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        j = json.loads(p.stdout)
        self.assertEqual((j["in_reply_to"], j["op"], j["from"]), ("self", "status", SELF))
        self.assertEqual(list(j["data"])[:5], ["identity", "usage", "keys", "fabric", "session"])
        self.assertNotIn("sk-or-secret-value", p.stdout)
        self.assertEqual(p.stdout, json.dumps(j, indent=2) + "\n")


def tempfile_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Actions(Daemon):
    def signed_registry(self, key) -> str:
        reg = os.path.join(self.scratch("agentd-reg-"), "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {WHO["host"]: {"operator": WHO["agent"], "operator_key": key["publicKeySpec"]}}, "placement": {}}, fh)
        return reg

    def upgrade_request(self, key, **over) -> str:
        return json.dumps(sign.sign_request(request_body(**{"from": SELF, "op": "upgrade", "args": {"piece": "claude", "version": "9.9.9"},
                                                            "ttl_s": 60, **over}), key["privateKeySpec"]))

    def test_once_a_signed_upgrade_already_started_is_waited_for_its_reply_is_posted_before_the_process_exits(self):
        k = sign.generate_operator_key()
        reg = self.signed_registry(k)
        home = self.home()
        os.makedirs(os.path.join(home, ".local", "bin"))
        # A slow harness already at the target: the action takes seconds and installs nothing.
        executable(os.path.join(home, ".local", "bin", "claude"), '#!/bin/sh\nsleep 2\necho "9.9.9 (Claude Code)"\n')
        state = os.path.join(home, "state")
        over = {"HOME": home, "AGENT_FABRIC_HOSTS_REGISTRY": reg, "AGENT_FABRIC_STATE_DIR": state}
        r = self.with_relay()
        signed = self.upgrade_request(k)
        out = self.once_after_wait(r, [(SELF, signed)], **over)
        self.assertEqual(out.status, 0, out.stderr)
        rs = [x for x in r.replies() if x["op"] == "upgrade"]
        self.assertEqual(len(rs), 1, f"the action's reply was posted before exit\n{out.stderr}")
        self.assertEqual((rs[0]["data"]["upgrade"]["status"], rs[0]["data"]["upgrade"]["version"]), ("current", "9.9.9"))
        self.assertRegex(out.stderr, r"agentd: started upgrade for \S+ \([0-9a-f]{8}\)")
        self.assertRegex(out.stderr, r"agentd: answered upgrade for \S+ \([0-9a-f]{8}\): current")
        # The ledger the daemon wrote, read back: the action's own timestamp.
        ledger = os.path.join(state, "agents", WHO["agent"], "actions-seen.json")
        sent = json.loads(signed)
        self.assertEqual(json.load(open(ledger))[sent["from"]], gzcoord_ts(sent["ts"]), "the daemon recorded the action in its ledger")
        # A new daemon (a restart: its in-memory LRU is empty) is shown the
        # same signed record again: refused, no second reply. After the NEW
        # daemon's first wait (r.until_waiting() already passed on the first run's).
        before = r.waits()
        threading.Thread(target=lambda: (r.until_waiting(before), r.add(sent["from"], signed)), daemon=True).start()
        again = self.run_once(r.url(), **over)
        self.assertEqual(len([x for x in r.replies() if x["op"] == "upgrade"]), 1, f"a replay after a restart got a reply\n{again.stderr}")
        self.assertRegex(again.stderr, r"not newer than the last action accepted .* \(a replay\)")

    def test_once_an_action_whose_ledger_cannot_be_written_is_refused_by_name_not_blamed_on_the_relay(self):
        k = sign.generate_operator_key()
        reg = self.signed_registry(k)
        home = self.home()
        state = os.path.join(home, "state")
        os.makedirs(state)
        open(os.path.join(state, "agents"), "w").write("not a directory")   # the ledger's directory cannot be made
        r = self.with_relay()
        out = self.once_after_wait(r, [(SELF, self.upgrade_request(k))], HOME=home, AGENT_FABRIC_HOSTS_REGISTRY=reg, AGENT_FABRIC_STATE_DIR=state)
        self.assertRegex(out.stderr, r"upgrade for .* refused: the action ledger could not be written \(ENOTDIR\)")
        self.assertNotIn("relay unreachable", out.stderr)
        self.assertEqual(len([x for x in r.replies() if x["op"] == "upgrade"]), 0, "nothing ran")

    def test_port_an_unsigned_or_misdated_action_is_never_run_and_never_recorded(self):
        k = sign.generate_operator_key()
        other = sign.generate_operator_key()
        reg = self.signed_registry(k)
        home = self.home()
        state = os.path.join(home, "state")
        r = self.with_relay()
        out = self.once_after_wait(r, [
            (SELF, json.dumps(request_body(**{"from": SELF, "op": "upgrade", "args": {"piece": "claude"}, "ttl_s": 60}))),
            (SELF, self.upgrade_request(other)),
            (SELF, self.upgrade_request(k, ts=iso(time.time() * 1000 + 300000)))],
            HOME=home, AGENT_FABRIC_HOSTS_REGISTRY=reg, AGENT_FABRIC_STATE_DIR=state)
        self.assertEqual(out.status, 0, out.stderr)
        self.assertEqual(r.replies(), [])
        self.assertEqual(out.stderr.count("not signed by"), 2, out.stderr)
        self.assertIn("in the future (the operator's clock?)", out.stderr)
        self.assertFalse(os.path.exists(os.path.join(state, "agents", WHO["agent"], "actions-seen.json")), "a refused action raises no floor")


class Resident(Daemon):
    def until(self, cond, what, daemon: subprocess.Popen, timeout: float = 20) -> None:
        end = time.monotonic() + timeout
        while not cond():
            if time.monotonic() > end:
                daemon.send_signal(signal.SIGTERM)
                raise AssertionError(f"{what}\n{daemon.communicate(timeout=20)[1]}")
            time.sleep(0.05)

    def test_the_resident_daemon_samples_memory_pressure_into_its_own_state_from_its_start_and_answers_it_in_host_once_samples_nothing(self):
        state = self.scratch("agentd-state-")
        ring = os.path.join(state, "agents", WHO["agent"], "memory-pressure.json")
        r = self.with_relay()
        once = self.run_once(r.url(), AGENT_FABRIC_STATE_DIR=state)
        self.assertEqual(once.status, 0, once.stderr)
        self.assertFalse(os.path.exists(ring), "--once leaves no ring")
        waits = r.waits()
        d = self.start(r.url(), AGENT_FABRIC_STATE_DIR=state)
        self.until(lambda: os.path.exists(ring), "no ring was written at start", d)
        self.assertEqual(len(json.load(open(ring))), 1, "one sample at start; the next a minute on")
        # After its prime: a request posted before it would be history to it.
        self.until(lambda: r.waits() > waits, "the daemon never waited", d)
        r.add("develop-qzapp/user", request(op="host"))
        self.until(lambda: any(x["op"] == "host" for x in r.replies()), "no host reply", d)
        mp = next(x for x in r.replies() if x["op"] == "host")["data"]["host"]["memory_pressure"]
        self.assertEqual(mp["status"], "ok", mp)
        self.assertEqual(mp["hour"]["samples"], 1)

    def test_the_resident_daemon_writes_the_tools_report_at_its_start_through_the_real_bin_fabric_tools_and_answers_it_in_tools_once_writes_none(self):
        state = self.scratch("agentd-state-")
        report = os.path.join(state, "agents", WHO["agent"], "tools.json")
        # bin/fabric-tools execs AGENT_FABRIC_PYTHON (its documented override
        # for a test): a fake interpreter, so no registry proof runs.
        doc = {"projects": ["gzapp"], "ok": False, "tools": [{"project": "gzapp", "name": "pnpm", "status": "missing", "found": "", "version": "11",
                                                              "where": "account", "optional": False, "why": "x"}]}
        py = os.path.join(self.scratch("agentd-py-"), "python")
        executable(py, f"#!/usr/bin/env bash\ncat <<'J'\n{json.dumps(doc)}\nJ\nexit 1\n")
        env = {"AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_PYTHON": py}
        r = self.with_relay()
        once = self.run_once(r.url(), **env)
        self.assertEqual(once.status, 0, once.stderr)
        self.assertFalse(os.path.exists(report), "--once writes no report")
        waits = r.waits()
        d = self.start(r.url(), **env)
        self.until(lambda: os.path.exists(report), "no tools report was written at start", d)
        self.assertEqual(json.load(open(report)), doc)
        self.until(lambda: r.waits() > waits, "the daemon never waited", d)
        r.add("develop-qzapp/user", request(op="tools"))
        self.until(lambda: any(x["op"] == "tools" for x in r.replies()), "no tools reply", d)
        t = next(x for x in r.replies() if x["op"] == "tools")["data"]["tools"]
        self.assertEqual(t["status"], "ok")
        self.assertEqual(t["tools"], doc["tools"])

    def test_port_the_resident_daemon_says_its_session_state_on_the_state_channel_not_the_control_channel(self):
        state = self.scratch("agentd-state-")
        r = self.with_relay()
        d = self.start(r.url(), AGENT_FABRIC_STATE_DIR=state, FABRIC_STATE_CHANNEL="test:state:control")
        self.until(lambda: r.waits() > 0, "the daemon never waited", d)
        self.until(lambda: any(h == "/api/send" for h in r.hits), "no state record posted", d)
        rec = next(json.loads(x["content"]) for x in r.rows if json.loads(x["content"]).get("kind") == "state")
        self.assertEqual(rec["from"], SELF)
        with r.lock:
            channels = [(c, json.loads(json.loads(b)["content"]).get("kind")) for c, b in r.posts]
        self.assertIn(("test:state:control", "state"), channels)
        self.assertNotIn(("test:control", "state"), channels, "a state record never rides the control channel")


    def test_port_sigterm_is_not_caught_the_process_ends_where_it_is(self):
        r = self.with_relay()
        d = self.start(r.url())
        self.until(lambda: r.waits() > 0, "the daemon never waited", d)
        d.send_signal(signal.SIGTERM)
        d.communicate(timeout=20)
        self.assertEqual(d.returncode, -signal.SIGTERM, "default disposition: ends where it is, as the Node did")

    def test_port_a_pull_that_changes_a_loaded_source_ends_the_daemon_for_systemd_after_the_quiet_period(self):
        # The daemon runs from a scratch copy of the code, so a "pull" is a
        # write to a file it has loaded.
        tree = self.scratch("agentd-tree-")
        for d in ("tools", "runtime", "communication", "identities", "bin", "projects"):
            if os.path.isdir(os.path.join(HERE, d)):
                shutil.copytree(os.path.join(HERE, d), os.path.join(tree, d), ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        r = self.with_relay()
        env = self.env(r.url())
        d = subprocess.Popen([sys.executable, os.path.join(tree, "tools", "fabric", "control", "agentd.py")], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(self._stop, d)
        self.until(lambda: r.waits() > 0, "the daemon never waited", d)
        with open(os.path.join(tree, "tools", "fabric", "control", "sessions.py"), "a") as fh:
            fh.write("\n# a pull\n")
        t0 = time.monotonic()
        try:
            _out, err = d.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("the daemon did not leave for new code")
        self.assertEqual(d.returncode, 0, err)
        self.assertIn("agentd: source changed; exiting for systemd to restart on the new code", err)
        self.assertGreaterEqual(time.monotonic() - t0, 1.5, "after the quiet period")



if __name__ == "__main__":
    unittest.main(verbosity=1)
