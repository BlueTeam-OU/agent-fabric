#!/usr/bin/env python3
"""Parity of the two daemons (ADR-040 Wave 8, step s6): runtime/control/agentd.mjs
and tools/fabric/control/agentd.py, each run with --once against its own fake
relay holding the same records — the same ids, the same signed requests — and
the same scratch home. What each posts is compared as the relay received it,
byte for byte, with only what differs by construction masked (message ids,
timestamps, the daemon's pid and uptime); what each says on stderr likewise,
less the relay's port. A side that does not start, exits non-zero or answers
nothing fails the suite: never an empty comparison.

The cases are the ones a reply is deterministic for: the reads that say what
a scratch home holds, and every action refused by its own module's argument
check (an accepted action reaches the account; the port's modules have their
own parity cases). The fence cases ride the same batch, so the refusal
reasons and their order on stderr are compared too.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from test_control_agentd import AGENTD, SELF, WHO, Daemon, iso, request_body  # noqa: E402
from control import sign  # noqa: E402

AGENTD_MJS = os.path.join(HERE, "runtime", "control", "agentd.mjs")
MASKS = [(re.compile(r'"id":"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"'), '"id":"ID"'),
         (re.compile(r'"ts":"\d{4}-\d\d-\d\dT[\d:.]+Z"'), '"ts":"TS"'),
         (re.compile(r'"started":"\d{4}-\d\d-\d\dT[\d:.]+Z"'), '"started":"TS"'),
         (re.compile(r'"pid":\d+'), '"pid":0'),
         (re.compile(r'"uptime_s":\d+'), '"uptime_s":0'),
         (re.compile(r'127\.0\.0\.1:\d+'), '127.0.0.1:PORT'),
         (re.compile(r'dated \d+ s in the future'), 'dated N s in the future')]   # the far-dated case: seconds since the batch was made


def masked(text: str) -> str:
    for rx, to in MASKS:
        text = rx.sub(to, text)
    return text


def memory_replies(replies):
    return [json.loads(r) for r in replies if json.loads(r)["op"] == "memory"]


def memory_view(replies):
    """What a memory answer says that does not depend on the zlib that
    deflated it: every record, masked, less the compressed bytes and what
    follows from their length (the bundle's gzip_bytes and parts, each part's
    chunk and its numbering, the first record's part count); the tar itself
    reassembled from the parts; and the gzip header, which no zlib build
    changes (the Python and the Node of a runner may link different builds)."""
    import base64
    import zlib
    gz = base64.b64decode("".join(r["data"]["part"]["chunk"] for r in replies[1:]))
    tar = zlib.decompress(gz, 31)

    def bare(r):
        r = json.loads(json.dumps(r))
        d = r["data"]
        d.pop("parts", None)
        for b in (d.get("memory") or {}).get("bundles", []):
            b.pop("gzip_bytes", None)
            b.pop("parts", None)
        if "part" in d:
            d["part"].pop("chunk")
            d["part"].pop("part")
            d["part"].pop("parts")
        return masked(json.dumps(r, separators=(",", ":")))
    return {"records": [bare(r) for r in replies], "tar": tar, "gzip_header": gz[:10], "parts_numbered": [r["data"]["part"]["part"] for r in replies[1:]]}


class Parity(Daemon):
    def batch(self, key) -> list[tuple[str, str]]:
        """Fixed ids, so each side's record is the same bytes."""
        n = [0]

        def plain(**over):
            n[0] += 1
            return (SELF, json.dumps(request_body(**{"id": f"parity-{n[0]:03d}", "from": SELF, **over})))

        def signed(**over):
            n[0] += 1
            body = request_body(**{"id": f"parity-{n[0]:03d}", "from": SELF, "ttl_s": 60, **over})
            return (SELF, json.dumps(sign.sign_request(body, key["privateKeySpec"])))
        stale = iso(time.time() * 1000 - 3600000)
        far = iso(time.time() * 1000 + 600000)
        rows = [
            plain(op="ping"), plain(op="identity"), plain(op="keys"), plain(op="tokens", days=3), plain(op="tokens", days=-1),
            plain(op="tokens", days=1000), plain(op="script"), plain(op="recall"), plain(op="memory"), plain(op="tools"),
            plain(op="pool-list"), plain(op="pool-claim", args={"id": "nope"}), plain(op="pool-add"),
            plain(op="local-prune", args={"x": 1}), plain(op="local-prune", args=[]),
            signed(op="upgrade", args={"piece": "nope"}), signed(op="secrets-sync", args={"x": 1}),
            signed(op="jobs-add", args={}), signed(op="tools-install", args={"tool": "../x"}),
            signed(op="secrets-selftest", args={"x": 1}), signed(op="pool-add", args={"x": 1}),
            signed(op="local-prune", args={"x": 1}),
            # refused by the fence, in the order the checks run
            plain(op="ping", to="elsewhere/other"), plain(op="shutdown"), plain(op="ping", ts=stale), plain(op="ping", v=2),
            plain(op="ping", id=""), plain(op="x" * 40), plain(op="ping", **{"from": "nobody/nothing"}),
            (SELF, "not json"), (SELF, json.dumps({"v": 1, "kind": "reply", "id": "r"})),
            plain(op="upgrade", args={"piece": "claude"}),
            signed(op="upgrade", args={"piece": "claude"}, ts=far),
            signed(op="upgrade", args={"piece": "claude"}, ts=stale),
        ]
        rows.append(rows[0])   # the same record again: seen, and quiet
        return rows

    def prepare(self):
        home = self.home()
        wc = os.path.join(home, "projects", "gzapp")
        os.makedirs(wc)
        from control.ops import memory_slug
        mem = os.path.join(home, ".claude", "projects", memory_slug(wc), "memory")
        os.makedirs(mem)
        open(os.path.join(mem, "a.md"), "w").write("x")
        fab = os.path.join(home, "projects", "agent-fabric", "tools", "fabric")
        os.makedirs(fab)
        open(os.path.join(fab, "payload.tar"), "wb").write(os.urandom(150 * 1024))
        open(os.path.join(fab, "harvest_memory.py"), "w").write(
            "import os, sys\nsys.stdout.buffer.write(open(os.path.join(os.path.dirname(__file__), 'payload.tar'), 'rb').read())\n"
            "sys.stderr.write('{\"claims\": 1, \"counts\": {\"in_scope\": 1, \"total\": 1}, \"needs_rendering\": [], \"skipped_no_roles_class\": []}')\n")
        key = sign.generate_operator_key()
        reg = os.path.join(self.scratch("agentd-reg-"), "registry.json")
        # the daemon's own account is the operator whose key signs: it may order what it signs
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {WHO["host"]: {"operator": WHO["agent"], "operator_key": key["publicKeySpec"]}},
                       "placement": {WHO["agent"]: WHO["host"]}}, fh)
        return home, reg, key

    def run_side(self, argv: list[str], home: str, reg: str, key, label: str):
        from test_control_agentd import FakeRelay
        r = FakeRelay([(SELF, json.dumps(request_body(op="ping", id="primer")))])
        self.addCleanup(r.close)
        state = self.scratch(f"agentd-state-{label}-")
        posts = self.batch(key)

        def later():
            try:
                r.until_waiting()
                for sender, content in posts:
                    r.add(sender, content)
            except AssertionError:
                pass
        threading.Thread(target=later, daemon=True).start()
        env = self.env(r.url(), HOME=home, AGENT_FABRIC_HOSTS_REGISTRY=reg, AGENT_FABRIC_STATE_DIR=state)
        p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=300, check=False, stdin=subprocess.DEVNULL)
        with r.lock:
            replies = [x["content"] for x in r.rows[1 + len(posts):]]
        return p, replies, state

    def test_the_two_daemons_post_the_same_bytes_and_say_the_same_things(self):
        home, reg, key = self.prepare()
        # one batch, made once, so both sides see the same signed bytes
        batch = self.batch(key)
        self.batch = lambda _k: batch
        node, node_replies, _ = self.run_side(["node", AGENTD_MJS, "--once"], home, reg, key, "node")
        py, py_replies, py_state = self.run_side([sys.executable, AGENTD, "--once"], home, reg, key, "py")
        self.assertEqual(node.returncode, 0, node.stderr)
        self.assertEqual(py.returncode, 0, py.stderr)
        self.assertGreater(len(node_replies), 20, "the Node side answered the batch (a side that answers nothing is no comparison)")
        self.assertEqual(len(py_replies), len(node_replies), f"{len(py_replies)} against {len(node_replies)}\n{py.stderr}")
        # An action answers beside the loop, when it is done: its place among
        # the replies is timing, in either daemon. Every other reply keeps its
        # request's order; each action's reply is compared with its own.
        from control.sign import ACTION_OPS

        def split(replies):
            plain = [r for r in replies if json.loads(r)["op"] not in ACTION_OPS]
            acts = {json.loads(r)["in_reply_to"]: r for r in replies if json.loads(r)["op"] in ACTION_OPS}
            return plain, acts
        (node_plain, node_acts), (py_plain, py_acts) = split(node_replies), split(py_replies)
        self.assertGreater(len(node_acts), 3, "the actions were answered")
        self.assertEqual(len(py_plain), len(node_plain))
        for i, (a, b) in enumerate(zip(node_plain, py_plain)):
            if json.loads(a)["op"] == "memory":
                continue   # below: the deflate stream is zlib's, which differs between zlib builds
            self.assertEqual(masked(b), masked(a), f"reply {i}: {json.loads(a).get('op')}")
        self.assertEqual(len(memory_replies(node_plain)), len(memory_replies(py_plain)), "the same number of memory records")
        self.assertEqual(*[memory_view(rs) for rs in (memory_replies(py_plain), memory_replies(node_plain))])
        self.assertEqual(sorted(py_acts), sorted(node_acts))
        for rid, a in node_acts.items():
            self.assertEqual(masked(py_acts[rid]), masked(a), f"action {rid}: {json.loads(a).get('op')}")
        # The same lines; the fence's refusals in the same order (the loop's),
        # the actions' lines in whatever order they finish.
        lines = lambda side: masked(side.stderr).splitlines()  # noqa: E731
        self.assertEqual(sorted(lines(py)), sorted(lines(node)))
        ignored = lambda side: [x for x in lines(side) if "ignored a record" in x]  # noqa: E731
        self.assertEqual(ignored(py), ignored(node))
        self.assertGreater(len(ignored(node)), 8, "the fence's refusals were exercised")
        # the ledger, the signed actions' replay defence, is the same file
        self.assertEqual(os.listdir(os.path.join(py_state, "agents", WHO["agent"])).count("actions-seen.json"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
