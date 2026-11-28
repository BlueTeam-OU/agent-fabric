#!/usr/bin/env python3
"""The account's transport mode file changes nothing in the inbox or the sender (InterWeave-only cutover plan row W15: the carrier
is the only transport), through the real bin/gzcoord-inbox and bin/gzcoord-send in the protocol suite's scratch environment
against a carrier stand-in. A running watch neither takes a changed mode nor says a word of one, a watch that starts on a damaged
file waits on the carrier as it would with none, and the sender goes out once through the carrier whatever the file holds. The
mode file's own cases are in tests/test_control_transport_mode.py; an account with no file reads carrier-only in
tests/test_gzcoord_interweave_only_config.py."""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — its carrier stand-in, scratch and command environment
from gzcoord.transport import mode  # noqa: E402

POLL_S = 0.5  # GZCOORD_MODE_POLL_S: the poll the watch had; set so a watch that still polled would say so inside the window
QUIET = 6 * POLL_S   # a window with no line in it: six of those polls


class Watch(unittest.TestCase):
    def setUp(self):
        self.carrier = P.Carrier(hold_s=0.2)      # holds each `wait` for a moment and lists nothing
        self.addCleanup(self.carrier.close)
        self.env = P.inbox_env(self.carrier, GZCOORD_UNTIL_DELIVERY_DOWN_S="30", GZCOORD_MODE_POLL_S=str(POLL_S))
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

    def waits(self) -> int:
        return self.carrier.ops().count("wait")

    def start(self, deadline=90):
        self.proc = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", str(deadline)], env=self.env, text=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(l.rstrip("\n")) for l in self.proc.stderr], daemon=True).start()
        end = time.monotonic() + 30
        while self.waits() < 1 and time.monotonic() < end and self.proc.poll() is None:
            time.sleep(0.05)
        self.assertGreaterEqual(self.waits(), 1, "the watch is waiting on the carrier")

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

    def test_a_running_watch_says_nothing_of_a_changed_or_damaged_mode_and_goes_on(self):
        self.start()
        for text in ('{"mode": "relay-record"}', "{", '{"mode": "carrier-record"}'):
            with open(self.file, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.assertIsNone(self.line_matching("transport", QUIET), f"no line for {text!r}")
        waits = self.waits()
        end = time.monotonic() + 10
        while self.waits() <= waits and time.monotonic() < end:
            time.sleep(0.1)
        self.assertGreater(self.waits(), waits, "the control: the watch still waits on the carrier, so the silence is not a stall")
        self.assertIsNone(self.proc.poll(), "and none of it ended the watch")

    def test_a_watch_that_starts_on_a_damaged_file_waits_on_the_carrier(self):
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("{")
        r = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "3"], env=self.env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("transport-mode.json", r.stdout + r.stderr)
        self.assertGreater(self.waits(), 0)


class Send(unittest.TestCase):
    def run_send(self, mode_text, carrier=True):
        stand_in = P.Carrier() if carrier else None
        if stand_in is not None:
            self.addCleanup(stand_in.close)
        base = P.scratch("mode-send-")
        agent = os.path.join(base, "state", "agents", P.LOGIN)
        os.makedirs(agent)
        if mode_text is not None:
            with open(os.path.join(agent, mode.FILE), "w", encoding="utf-8") as fh:
                fh.write(mode_text)
        f = os.path.join(base, "m.txt")
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(P.VALID)
        r = P.run_cmd(P.SEND_CMD, [f], P.send_env(stand_in, base))
        return r, stand_in, agent

    def test_a_mode_file_of_any_content_or_none_the_send_goes_out_once_through_the_carrier(self):
        for text in (None, "{", '{"mode": "relay-record"}', '{"mode": "carrier-record"}', '{"mode": "carrier-only"}', '{"mode": "nonsense"}'):
            r, carrier, agent = self.run_send(text)
            self.assertEqual((r.code, [x["message_id"] for x in carrier.posts]), (0, [P.VALID_ID]), (text, r.err))
            self.assertNotIn("transport-mode.json", r.err, text)

    def test_with_no_carrier_the_send_is_not_sent_whatever_the_mode_file_says(self):
        for text in (None, '{"mode": "relay-record"}'):
            r, _, agent = self.run_send(text, carrier=False)
            self.assertEqual(r.code, 3, (text, r.err))
            self.assertIn("the InterWeave carrier is not running", r.err)
            self.assertIn("not sent", r.err)


def tearDownModule():
    # The protocol suite removes its scratch only at the end of its own main(); imported here, nothing else would, and the
    # run's "scratch left behind" check (tests/run.py) fails the suite that leaves any.
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
