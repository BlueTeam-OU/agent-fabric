#!/usr/bin/env python3
"""bin/fabric-op and `fabric-ctl <login> <action-op> --via hostexec`
(tools/fabric/control/breakglass.py): the break-glass path to an account with
no relay.

Two kinds of case. The decision cases call run_target() in this process with a
registry, a ledger and a journal of the case's own, and a counting stand-in for
agentd.answer(): what they prove is that nothing ran, with the reason said, for
each defect, and that the same request WITHOUT the defect runs (so a check that
passes by never being reached shows). The end-to-end cases run the real
runtime/hostexec/hostexec (local backend, a fixture registry) into the real
bin/fabric-op, and the operator side through ctl.main(), with a minimal explicit
environment and the one real action `local-prune` against an empty home.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import agentd, breakglass, ctl, sign  # noqa: E402
from control.gzcoord import whoami  # noqa: E402

HOSTEXEC = os.path.join(HERE, "runtime", "hostexec", "hostexec")
FABRIC_OP = os.path.join(HERE, "bin", "fabric-op")
HOST, ACCOUNT, OPERATOR = "h1", "acct", "op"
ME = {"address": f"{HOST}/{ACCOUNT}"}
OP_ADDRESS = f"{HOST}/{OPERATOR}"
KEY = sign.generate_operator_key()
OTHER_KEY = sign.generate_operator_key()


def iso(ms: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{int(ms) % 1000:03d}Z"


class Scratch(unittest.TestCase):
    def scratch(self) -> str:
        d = tempfile.mkdtemp(prefix="breakglass-")
        self.addCleanup(shutil.rmtree, d, True)
        return d


def registry_file(d: str, host: str = HOST, account: str = ACCOUNT, key: dict = KEY, fabric: str = HERE) -> str:
    path = os.path.join(d, "registry.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "hosts": {host: {"platform": "debian", "ssh": None, "operator": OPERATOR, "fabric": fabric,
                                                  "operator_key": key["publicKeySpec"]}},
                   "placement": {account: host, OPERATOR: host}}, fh)
    return path


def action(*, signer: dict | None = KEY, **over) -> dict:
    body = {"v": 1, "kind": "request", "id": agentd.new_id(), "from": OP_ADDRESS, "to": [ME["address"]], "op": "local-prune",
            "ts": iso(time.time() * 1000), "ttl_s": 30, **over}
    return sign.sign_request(body, signer["privateKeySpec"]) if signer else body


class Fake:
    """A stand-in for agentd.answer(): counts the calls and answers as an action does."""

    def __init__(self, status: str = "pruned", raises: Exception | None = None):
        self.calls: list[dict] = []
        self.status, self.raises = status, raises

    def __call__(self, request, ctx):
        self.calls.append(request)
        if self.raises:
            raise self.raises
        return {"v": 1, "kind": "reply", "id": agentd.new_id(), "in_reply_to": request["id"], "from": ctx["me"]["address"],
                "op": request["op"], "ts": iso(time.time() * 1000), "ok": True, "data": {request["op"]: {"status": self.status}},
                "_followups": []}


class Target(Scratch):
    def setUp(self):
        self.d = self.scratch()
        self.registry = registry_file(self.d)
        self.journal = os.path.join(self.d, "state", "fabric-op.jsonl")
        self.ledger = agentd.ActionLedger(os.path.join(self.d, "state", "actions-seen.json"))
        self.fake = Fake()
        p = mock.patch.object(agentd, "answer", self.fake)
        p.start()
        self.addCleanup(p.stop)

    def run_op(self, request, argv=None, raw=None, **kw):
        out, err = io.StringIO(), io.StringIO()
        data = raw if raw is not None else (json.dumps(request) if isinstance(request, dict) else request).encode("utf-8")
        rc = breakglass.run_target(["local-prune"] if argv is None else argv, io.BytesIO(data), out, err, me=ME, journal=self.journal,
                                   ledger=self.ledger, registry=self.registry, **kw)
        return rc, out.getvalue(), err.getvalue()

    def lines(self):
        try:
            with open(self.journal, encoding="utf-8") as fh:
                return [json.loads(ln) for ln in fh]
        except FileNotFoundError:
            return []

    def accepted(self, request, **kw):
        rc, out, err = self.run_op(request, **kw)
        self.assertEqual((rc, err), (0, ""), (out, err))
        return out

    def refused(self, request, why, **kw):
        before = len(self.fake.calls)
        rc, out, err = self.run_op(request, **kw)
        self.assertEqual((rc, out), (2, ""), err)
        self.assertRegex(err, r"^fabric-op: refused: .*" + why + r".*\n$")
        self.assertEqual(err.count("\n"), 1, "one line")
        self.assertEqual(len(self.fake.calls), before, "nothing ran")


class Decision(Target):
    def test_a_signed_action_runs_prints_the_reply_and_journals_twice(self):
        r = action()
        out = self.accepted(r)
        reply = json.loads(out)
        self.assertEqual(out.count("\n"), 1)
        self.assertEqual((reply["kind"], reply["in_reply_to"], reply["from"]), ("reply", r["id"], ME["address"]))
        self.assertNotIn("_followups", reply)
        self.assertEqual(self.fake.calls, [r])
        before, after = self.lines()
        self.assertEqual(list(before), ["v", "phase", "at", "id", "op", "from", "to", "host", "ts", "via"])
        self.assertEqual((before["phase"], before["id"], before["op"], before["from"], before["to"], before["host"], before["ts"], before["via"]),
                         ("before", r["id"], "local-prune", OP_ADDRESS, [ME["address"]], HOST, r["ts"], "fabric-op"))
        self.assertEqual(list(after), ["v", "phase", "at", "id", "status", "exit"])
        self.assertEqual((after["phase"], after["id"], after["status"], after["exit"]), ("after", r["id"], "ok", 0))
        self.assertEqual(os.stat(self.journal).st_mode & 0o777, 0o600)

    def test_each_defect_is_refused_with_its_reason_nothing_run_and_the_request_without_it_is_accepted(self):
        now = time.time() * 1000
        cases = [
            ("unsigned", lambda **o: action(signer=None, **o), "not signed by", {}),
            ("signed by another key", lambda **o: action(signer=OTHER_KEY, **o), "not signed by", {}),
            ("a sender that is no operator", lambda **o: action(**{"from": f"{HOST}/{ACCOUNT}", **o}), "is not an operator", {}),
            ("expired", lambda **o: action(**{"ts": iso(now - 100000), **o}), "expired", {}),
            ("dated beyond the skew", lambda **o: action(**{"ts": iso(now + 120000), **o}), "in the future", {}),
            ("addressed to everyone", lambda **o: action(**{"to": "*", **o}), "must name h1/acct explicitly, not", {}),
            ("everyone in a list", lambda **o: action(**{"to": ["*", ME["address"]], **o}), "must name h1/acct explicitly", {}),
            ("another account", lambda **o: action(**{"to": [f"{HOST}/other"], **o}), "not for me", {}),
            ("a read op", lambda **o: action(signer=None, **{"op": "ping", **o}), "not an action op", {"argv": ["ping"]}),
            ("an argv op that is not the request's", lambda **o: action(**o), "the request is for local-prune", {"argv": ["restart"]}),
        ]
        for label, make, why, kw in cases:
            with self.subTest(label):
                self.refused(make(), why, **kw)
                good = action()
                self.accepted(good)
                self.assertEqual(self.fake.calls[-1], good, f"the control for {label}")

    def test_a_signature_openssl_cannot_check_is_a_refusal_not_a_run(self):
        with mock.patch.object(agentd, "verify_request", side_effect=sign.SignError("openssl is not installed")):
            self.refused(action(), r"the signature could not be checked \(openssl is not installed\)")
        self.accepted(action())

    def test_the_control_of_a_wildcard_and_a_list_naming_this_account_among_others(self):
        self.accepted(action(to=[ME["address"], f"{HOST}/other"]))

    def test_replay_after_a_relay_accept_and_after_a_fabric_op_accept_is_refused_by_the_one_ledger(self):
        ts = iso(time.time() * 1000)
        # agentd's path: accepted, and recorded before it ran
        a = agentd.accept({"content": json.dumps(action(ts=ts))}, me=ME, operators={OP_ADDRESS}, keys=lambda: agentd.operator_keys(self.registry),
                          ttl_s=30, seen=set(), action_floor=self.ledger.floor)
        self.assertTrue(a["ok"], a)
        self.ledger.record(OP_ADDRESS, a["ts"])
        self.refused(action(ts=ts), "a replay")
        newer = action(ts=iso(time.time() * 1000 + 5))
        self.accepted(newer)
        # and the other way: fabric-op's accept is a replay for agentd's own check
        again = agentd.accept({"content": json.dumps(newer)}, me=ME, operators={OP_ADDRESS}, keys=lambda: agentd.operator_keys(self.registry),
                              ttl_s=30, seen=set(), action_floor=self.ledger.floor)
        self.assertRegex(again["why"], r"\(a replay\)$")
        self.refused(newer, "a replay")
        self.refused(action(ts=newer["ts"]), "a replay")

    def test_two_copies_that_pass_the_floor_check_together_run_once(self):
        barrier = threading.Barrier(2)

        class Meeting(agentd.ActionLedger):
            def floor(self, sender):
                f = super().floor(sender)
                barrier.wait(5)   # both have read the floor before either claims
                return f
        ledger = Meeting(self.ledger.file)
        r = action()
        results: list = []

        def go():
            out, err = io.StringIO(), io.StringIO()
            rc = breakglass.run_target(["local-prune"], io.BytesIO(json.dumps(r).encode()), out, err, me=ME, journal=self.journal,
                                       ledger=ledger, registry=self.registry)
            results.append((rc, err.getvalue()))
        threads = [threading.Thread(target=go) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(sorted(rc for rc, _ in results), [0, 2], results)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertRegex(next(e for rc, e in results if rc == 2), r"a replay")

    def test_an_unwritable_journal_refuses_the_run_and_does_not_spend_the_request(self):
        os.makedirs(self.journal)   # a directory where the file goes: unwritable for any user
        r = action()
        self.refused(r, r"the journal .* could not be written \(EISDIR\); nothing run")
        self.assertEqual(self.ledger.floor(OP_ADDRESS), 0, "the ledger was not claimed")
        os.rmdir(self.journal)
        self.accepted(r)   # the same signed request, the journal fixed
        self.assertEqual(self.fake.calls, [r])

    def test_an_unwritable_ledger_refuses_by_name_and_runs_nothing(self):
        with mock.patch.object(self.ledger, "claim", side_effect=PermissionError(13, "denied")):
            self.refused(action(), r"the action ledger could not be written \(EACCES\); nothing run")

    def test_a_refusal_is_journaled_when_it_can_be_with_its_reason_and_no_before_line(self):
        r = action(signer=None)
        self.refused(r, "not signed by")
        (line,) = self.lines()
        self.assertEqual((line["phase"], line["id"], line["status"], line["exit"]), ("after", r["id"], "refused", 2))
        self.assertIn("not signed by", line["reason"])

    def test_an_op_that_fails_exits_1_prints_its_reply_and_journals_failed(self):
        self.fake.status = "failed"
        rc, out, err = self.run_op(action())
        self.assertEqual((rc, err), (1, ""))
        self.assertEqual(json.loads(out)["data"]["local-prune"]["status"], "failed")
        self.assertEqual([ln.get("status") for ln in self.lines()], [None, "failed"])

    def test_an_op_that_raises_exits_1_with_one_line_and_journals_error(self):
        self.fake.raises = RuntimeError("disk gone")
        rc, out, err = self.run_op(action())
        self.assertEqual((rc, out, err), (1, "", "fabric-op: local-prune failed: disk gone\n"))
        self.assertEqual(self.lines()[-1]["status"], "error")

    def test_stdin_is_bounded_and_must_be_one_utf8_request(self):
        for raw, why in ((b"", "no request on stdin"), (b"x" * (breakglass.MAX_REQUEST_BYTES + 1), "larger than"),
                         (b"\xff\xfe", "not UTF-8"), (b"{not json", "not json")):
            with self.subTest(raw[:10]):
                self.refused(None, why, raw=raw)
        self.refused(None, "usage", raw=b"{}", argv=[])
        self.refused(None, "usage", raw=b"{}", argv=["a", "b"])
        self.refused(None, "usage", raw=b"{}", argv=["--x"])
        self.accepted(action(), raw=json.dumps(action()).encode() + b"\n" * 100)


class Ledger(Scratch):
    def test_a_writer_waits_for_the_lock_and_proceeds_when_it_is_released(self):
        ledger = agentd.ActionLedger(os.path.join(self.scratch(), "s", "actions-seen.json"))
        done = threading.Event()
        with ledger._locked():
            t = threading.Thread(target=lambda: (ledger.record("a/b", 5), done.set()))
            t.start()
            self.assertFalse(done.wait(0.4), "the write waits while another holds the ledger")
        self.assertTrue(done.wait(5))
        t.join(5)
        self.assertEqual(ledger.floor("a/b"), 5)

    def test_a_holder_that_does_not_let_go_is_an_error_the_caller_can_say(self):
        ledger = agentd.ActionLedger(os.path.join(self.scratch(), "s", "actions-seen.json"))
        with mock.patch.object(agentd, "LEDGER_LOCK_WAIT_S", 0.2), ledger._locked():
            with self.assertRaises(OSError) as cm:
                ledger.claim("a/b", 5)
        self.assertEqual(cm.exception.errno, __import__("errno").ETIMEDOUT)
        self.assertEqual(ledger.floor("a/b"), 0)

    def test_claim_says_whether_the_timestamp_was_newer_and_record_never_lowers_a_floor(self):
        ledger = agentd.ActionLedger(os.path.join(self.scratch(), "s", "actions-seen.json"))
        self.assertTrue(ledger.claim("a/b", 10))
        self.assertFalse(ledger.claim("a/b", 10))
        self.assertFalse(ledger.claim("a/b", 9))
        ledger.record("a/b", 3)
        self.assertEqual(ledger.floor("a/b"), 10)
        self.assertTrue(ledger.claim("a/b", 11))
        self.assertEqual(os.listdir(os.path.dirname(ledger.file)), ["actions-seen.json"], "the lock leaves no file")

    def test_writers_in_separate_processes_keep_the_highest_floor(self):
        f = os.path.join(self.scratch(), "s", "actions-seen.json")
        code = ("import sys; sys.path.insert(0, %r); from control import agentd\n"
                "l = agentd.ActionLedger(sys.argv[1])\n"
                "for i in range(int(sys.argv[2]), int(sys.argv[3])): l.record('a/b', i)\n") % os.path.join(HERE, "tools", "fabric")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "AGENT_FABRIC_STATE_DIR": os.path.dirname(f)}
        procs = [subprocess.Popen([sys.executable, "-c", code, f, str(lo), str(hi)], env=env) for lo, hi in ((1, 200), (200, 400), (1, 400))]
        for p in procs:
            self.assertEqual(p.wait(120), 0)
        self.assertEqual(agentd.ActionLedger(f).floor("a/b"), 399)


def minimal_env(d: str, registry: str, state: str) -> dict:
    home = os.path.join(d, "home")
    os.makedirs(home, exist_ok=True)
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "AGENT_FABRIC_PYTHON": sys.executable,
            "AGENT_FABRIC_HOSTS_REGISTRY": registry, "AGENT_FABRIC_STATE_DIR": state}


WHO = whoami()
LOCAL_HOST, LOCAL_LOGIN = WHO["host"], WHO["agent"]


class EndToEnd(Scratch):
    """The real hostexec (local backend) into the real bin/fabric-op, this login as the target account."""

    def setUp(self):
        self.d = self.scratch()
        self.registry = registry_file(self.d, host=LOCAL_HOST, account=LOCAL_LOGIN)
        self.state = os.path.join(self.d, "state")
        self.env = minimal_env(self.d, self.registry, self.state)
        self.op_journal = os.path.join(self.d, "operator-state", "fabric-op.jsonl")
        self.target = f"{LOCAL_HOST}/{LOCAL_LOGIN}"
        self.sender = f"{LOCAL_HOST}/{OPERATOR}"

    def request(self, **over):
        return action(**{"from": self.sender, "to": [self.target], **over})

    def hostexec(self, request, op="local-prune"):
        body = request if isinstance(request, bytes) else json.dumps(request).encode()
        p = subprocess.run([HOSTEXEC, LOCAL_HOST, "--as", LOCAL_LOGIN, "--", "@fabric/bin/fabric-op", op], input=body, env=self.env,
                           capture_output=True, timeout=120, check=False)
        return p.returncode, p.stdout.decode(), p.stderr.decode()

    def target_journal(self):
        files = [os.path.join(r, n) for r, _, ns in os.walk(self.state) for n in ns if n == "fabric-op.jsonl"]
        self.assertLessEqual(len(files), 1, files)
        with open(files[0], encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh]

    def test_a_signed_action_runs_through_hostexec_prints_its_reply_and_journals_twice(self):
        r = self.request()
        rc, out, err = self.hostexec(r)
        self.assertEqual((rc, err), (0, ""), out)
        reply = json.loads(out)
        self.assertEqual((reply["in_reply_to"], reply["from"], reply["op"]), (r["id"], self.target, "local-prune"))
        self.assertIn(reply["data"]["local-prune"]["status"], ("pruned", "clean"))
        self.assertEqual([ln["phase"] for ln in self.target_journal()], ["before", "after"])
        rc, out, err = self.hostexec(r)
        self.assertEqual((rc, out), (2, ""))
        self.assertRegex(err, r"^fabric-op: refused: local-prune: not newer than the last action accepted from .*\(a replay\)\n$")

    def test_a_defect_through_the_real_entry_point_is_a_refusal_with_exit_2_and_stdin_never_in_argv(self):
        for label, r in (("unsigned", self.request(signer=None)), ("wildcard", self.request(to="*"))):
            with self.subTest(label):
                rc, out, err = self.hostexec(r)
                self.assertEqual((rc, out), (2, ""))
                self.assertTrue(err.startswith("fabric-op: refused: "), err)
        rc, out, err = self.hostexec(self.request(), op="restart")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("the request is for local-prune", err)
        self.assertEqual(self.hostexec(self.request())[0], 0, "the control")

    def operator_side(self, argv, signer=KEY, **kw):
        out, err = [], []
        with mock.patch.object(ctl, "signing_key", return_value={"key": signer["privateKeySpec"]} if signer else {"error": "no key"}), \
                mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(breakglass, "journal_file", return_value=self.op_journal), \
                mock.patch.object(ctl, "api", side_effect=AssertionError("the relay is never touched")), \
                mock.patch.object(ctl, "gz_token", side_effect=AssertionError("no token is read")), \
                mock.patch.object(ctl, "synced_token", side_effect=AssertionError("no token is read")):
            rc = ctl.main(argv, registry=self.registry, who={"host": LOCAL_HOST, "agent": OPERATOR}, out=out.append, err=err.append, **kw)
        return rc, out, err

    def op_lines(self):
        with open(self.op_journal, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh]

    def test_fabric_ctl_via_hostexec_signs_sends_prints_the_relay_row_and_journals_on_both_ends_without_the_relay_or_a_token(self):
        rc, out, err = self.operator_side([LOCAL_LOGIN, "local-prune", "--via", "hostexec"])
        self.assertEqual((rc, err), (0, []), out)
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], LOCAL_LOGIN)
        before, after = self.op_lines()
        self.assertEqual((before["phase"], before["via"], before["host"], before["op"], before["from"], before["to"]),
                         ("before", "hostexec", LOCAL_HOST, "local-prune", self.sender, [self.target]))
        self.assertEqual((after["phase"], after["id"], after["status"], after["exit"]), ("after", before["id"], "ok", 0))
        t_before, t_after = self.target_journal()
        self.assertEqual((t_before["id"], t_before["via"], t_after["status"]), (before["id"], "fabric-op", "ok"))

    def test_the_row_is_the_one_a_relay_reply_makes(self):
        reply = {"v": 1, "kind": "reply", "id": "r", "in_reply_to": "x", "from": self.target, "op": "local-prune", "ok": True,
                 "data": {"local-prune": {"status": "pruned", "working_copies": []}}}
        relay_row = ctl.table("local-prune", ctl.rows([{"login": LOCAL_LOGIN, "host": LOCAL_HOST, "address": self.target}], [dict(reply, latency_ms=3)]))
        with mock.patch.object(breakglass, "via_hostexec", side_effect=lambda request, target, **kw: breakglass.Outcome("reply", dict(reply, in_reply_to=request["id"]), exit=0)):
            rc, out, err = self.operator_side([LOCAL_LOGIN, "local-prune", "--via", "hostexec"])
        self.assertEqual((rc, "\n".join(out)), (0, relay_row))

    def test_json_rows_and_an_op_that_failed_exit_1(self):
        reply = {"kind": "reply", "from": self.target, "op": "local-prune", "data": {"local-prune": {"status": "failed", "reason": "x"}}}
        with mock.patch.object(breakglass, "via_hostexec", return_value=breakglass.Outcome("reply", reply, exit=1)):
            rc, out, err = self.operator_side(["--json", LOCAL_LOGIN, "local-prune", "--via", "hostexec"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out[0])["account"], LOCAL_LOGIN)

    def test_an_unsigned_action_is_never_sent(self):
        with mock.patch.object(breakglass, "via_hostexec", side_effect=AssertionError("sent")):
            rc, out, err = self.operator_side([LOCAL_LOGIN, "local-prune", "--via", "hostexec"], signer=None)
        self.assertEqual((rc, out), (3, []))
        self.assertIn("an action is signed or not sent", err[0])
        self.assertFalse(os.path.exists(self.op_journal))

    def test_the_target_refusal_comes_back_as_exit_2_with_its_reason_and_both_journals_say_refused(self):
        rc, out, err = self.operator_side([LOCAL_LOGIN, "local-prune", "--via", "hostexec"], signer=OTHER_KEY)
        self.assertEqual((rc, out), (2, []))
        self.assertRegex(err[0], r"refused by fabric-op: local-prune: not signed by")
        self.assertEqual(self.op_lines()[-1]["status"], "refused")
        self.assertEqual(self.target_journal()[-1]["status"], "refused")

    def test_an_unwritable_operator_journal_sends_nothing(self):
        os.makedirs(self.op_journal)
        rc, out, err = self.operator_side([LOCAL_LOGIN, "local-prune", "--via", "hostexec"])
        self.assertEqual((rc, out), (3, []))
        self.assertRegex(err[0], r"could not be written .*; nothing sent")
        self.assertFalse(os.path.exists(self.state), "the target was never reached")

    def test_via_is_refused_for_a_read_for_everyone_and_for_a_path_that_is_not_hostexec(self):
        for argv, why in (([LOCAL_LOGIN, "status", "--via", "hostexec"], "an action op only"),
                          (["all", "local-prune", "--via", "hostexec"], "names one login"),
                          ([LOCAL_LOGIN, "local-prune", "--via", "ssh"], "--via takes hostexec")):
            with self.subTest(argv):
                rc, out, err = self.operator_side(argv)
                self.assertEqual((rc, out), (2, []))
                self.assertIn(why, err[0])

    def test_help_names_via_for_an_action_verb_and_not_for_a_read(self):
        self.assertIn("--via hostexec", ctl.render_help("restart"))
        self.assertNotIn("--via", ctl.render_help("status"))
        self.assertEqual(ctl.parse_args(["x", "restart", "--via=hostexec"])["via"], "hostexec")
        self.assertNotIn("via", ctl.parse_args(["x", "restart"]))

    def test_hostexec_outcomes_other_than_a_reply(self):
        target = {"login": LOCAL_LOGIN, "host": LOCAL_HOST, "address": self.target}
        r = self.request()
        j = os.path.join(self.d, "j", "fabric-op.jsonl")

        def done(rc, out=b"", err=b""):
            return lambda *a, **k: subprocess.CompletedProcess(a, rc, out, err)

        def timeout(*a, **k):
            raise subprocess.TimeoutExpired(a, 1)
        cases = [(done(2, err=b"hostexec: unknown host 'zz'\n"), "failed", "unknown host"),
                 (done(0, out=b"not json\n"), "failed", "exit 0 with no reply record"),
                 (done(0, out=json.dumps({"kind": "reply", "in_reply_to": "other", "from": self.target}).encode()), "failed", "no reply record"),
                 (done(2, err=b"fabric-op: refused: because\n"), "refused", "because"),
                 (timeout, "no-answer", "may still be running"),
                 (done(1, out=json.dumps({"kind": "reply", "in_reply_to": r["id"], "from": f"{LOCAL_HOST}/someone"}).encode()), "failed", "no reply record")]
        for run, kind, detail in cases:
            with self.subTest(kind, detail=detail):
                o = breakglass.via_hostexec(r, target, timeout=1, journal=j, run=run)
                self.assertEqual(o.kind, kind)
                self.assertIn(detail, o.detail)
        # the request travels on stdin, the argument list names only the op
        seen = {}

        def spy(argv, **k):
            seen.update(argv=argv, input=k["input"], timeout=k["timeout"])
            return subprocess.CompletedProcess(argv, 2, b"", b"fabric-op: refused: x\n")
        breakglass.via_hostexec(r, target, timeout=7, journal=j, run=spy)
        self.assertEqual(seen["argv"][1:], [LOCAL_HOST, "--as", LOCAL_LOGIN, "--", "@fabric/bin/fabric-op", "local-prune"])
        self.assertEqual(json.loads(seen["input"]), r)
        self.assertEqual(seen["timeout"], 7)
        self.assertNotIn(r["sig"], " ".join(seen["argv"]))


if __name__ == "__main__":
    unittest.main()
