#!/usr/bin/env python3
"""A running watch takes a changed transport mode (InterWeave-only cutover plan row W5), through the real bin/gzcoord-inbox in the
protocol suite's scratch environment against a stub relay that holds nothing: the account's mode is changed while the
watch waits, and the watch says so within the minute the plan allows. A mode that cannot be read ends a starting watch with exit 7
and its reason on stdout, and is said once and not obeyed by a running one. The mode file's own cases and open_transport's are in
tests/test_control_transport_mode.py. The sender refuses on such a file before it keeps or posts anything."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — its relay stub, scratch and command environment
from gzcoord.transport import mode  # noqa: E402

WITHIN = 60   # the plan's bound: "a running watch takes a changed mode within a minute"


class Watch(unittest.TestCase):
    def setUp(self):
        self.waits = 0

        def answer(_h, method, path, body):
            if path.startswith("/api/wait"):
                self.waits += 1
                time.sleep(0.2)      # a relay that holds nothing, without spinning the watch
                return 200, json.dumps({"messages": []})
            return 200, "{}"
        self.stub = P.Stub(answer)
        self.addCleanup(self.stub.close)
        self.env = P.cmd_env(CLAUDE_BRIDGE_URL=self.stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                             AGENT_FABRIC_SECRET_STORE=P.id_store(), GZCOORD_UNTIL_DELIVERY_DOWN_S="30")
        saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
        os.environ["AGENT_FABRIC_STATE_DIR"] = self.env["AGENT_FABRIC_STATE_DIR"]
        try:
            self.dir = os.path.dirname(mode.path())      # this login's state directory in the case's scratch
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = saved
        os.makedirs(self.dir, exist_ok=True)
        self.file = os.path.join(self.dir, mode.FILE)

    def start(self, deadline=90):
        self.proc = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", str(deadline)], env=self.env, text=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(l.rstrip("\n")) for l in self.proc.stderr], daemon=True).start()
        end = time.monotonic() + 30
        while self.waits < 1 and time.monotonic() < end and self.proc.poll() is None:
            time.sleep(0.05)
        self.assertGreaterEqual(self.waits, 1, "the watch is waiting on the relay")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        for pipe in (self.proc.stdout, self.proc.stderr):
            pipe.close()

    def line_matching(self, needle, within):
        end = time.monotonic() + within
        while time.monotonic() < end:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if needle in line:
                return line
        return None

    def test_a_changed_mode_is_taken_within_a_minute_and_the_watch_goes_on(self):
        self.start()
        mode.write("carrier-record", "h1/op", self.dir)
        t0 = time.monotonic()
        line = self.line_matching("transport mode is now carrier-record", WITHIN)
        self.assertIsNotNone(line, "the watch did not take the change")
        self.assertLess(time.monotonic() - t0, WITHIN)
        waits = self.waits
        end = time.monotonic() + 10
        while self.waits <= waits and time.monotonic() < end:
            time.sleep(0.1)
        self.assertGreater(self.waits, waits, "the watch waits on the relay again after the change")
        self.assertIsNone(self.proc.poll(), "taking a mode does not end the watch")
        mode.write("carrier-only", "h1/op", self.dir)
        self.assertIsNotNone(self.line_matching("transport mode is now carrier-only", WITHIN), "a second change is taken as well")

    def test_a_watch_that_is_not_moved_says_nothing_of_modes(self):
        self.start()
        self.assertIsNone(self.line_matching("transport mode", 12), "the control: no change, no line (poll interval is 5 s)")
        mode.write("carrier-record", "h1/op", self.dir)       # the positive control: the same watch does see a change
        self.assertIsNotNone(self.line_matching("transport mode is now carrier-record", WITHIN))

    def test_a_mode_that_cannot_be_read_is_said_once_and_not_obeyed_by_a_running_watch(self):
        mode.write("carrier-record", "h1/op", self.dir)      # not the default: reading damage as relay-record would be a visible move
        self.start()
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("{")
        self.assertIsNotNone(self.line_matching("the watch keeps transport mode carrier-record", WITHIN), "the damage is said")
        self.assertIsNone(self.line_matching("transport mode is now", 12), "and not obeyed, nor said again")
        self.assertIsNone(self.proc.poll())
        mode.write("carrier-only", "h1/op", self.dir)
        self.assertIsNotNone(self.line_matching("transport mode is now carrier-only", WITHIN))

    def test_a_watch_that_starts_on_a_damaged_file_ends_with_exit_7_and_says_why_on_stdout(self):
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("{")
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "20"], env=self.env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertIn("transport-mode.json", r.stdout)
        self.assertEqual(self.waits, 0, "nothing was fetched from the relay")
        os.unlink(self.file)     # the positive control: with no file the same command starts and waits
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "3"], env=self.env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreater(self.waits, 0)


class Send(unittest.TestCase):
    def run_send(self, mode_text):
        relay = P.Relay()
        self.addCleanup(relay.close)
        base = P.scratch("mode-send-")
        agent = os.path.join(base, "state", "agents", P.LOGIN)
        os.makedirs(agent)
        if mode_text is not None:
            with open(os.path.join(agent, mode.FILE), "w", encoding="utf-8") as fh:
                fh.write(mode_text)
        f = os.path.join(base, "m.txt")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(P.VALID)
        r = P.run_cmd(P.SEND_CMD, [f], P.send_env(relay.url, base))
        return r, relay, agent

    def test_a_mode_that_cannot_be_read_is_not_sent_not_kept_and_says_how_to_repair_it(self):
        r, relay, agent = self.run_send("{")
        self.assertEqual(r.code, 2, r.err)
        self.assertIn("transport-mode.json", r.err)
        self.assertEqual((r.out, relay.posts), ("", []))
        self.assertFalse(os.path.exists(os.path.join(agent, "gzcoord-sent.jsonl")), "nothing was recorded as sent")
        self.assertFalse(os.path.exists(os.path.join(agent, "episodic.db")), "no journal row was kept to stay pending")

    def test_with_no_mode_file_or_any_good_one_the_same_send_goes_out_once(self):
        for text in (None, '{"mode": "relay-record"}', '{"mode": "carrier-only"}'):
            r, relay, agent = self.run_send(text)
            self.assertEqual((r.code, len(relay.posts)), (0, 1), (text, r.err))


if __name__ == "__main__":
    unittest.main()
