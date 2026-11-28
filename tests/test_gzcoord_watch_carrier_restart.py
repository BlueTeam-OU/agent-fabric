#!/usr/bin/env python3
"""A watch rides out carrier restarts (j169). The fleet upgrade restarts interweave-client under every running
`gzcoord-inbox --until-delivery`; the watch must count its silence bound from the first failure after the carrier's LAST ANSWER,
not from the first failure of an earlier outage, and must neither exit nor lose a message across a restart.

The real bin/gzcoord-inbox against a fake carrier on its adapter socket, in the protocol suite's scratch environment, with a
short give-up bound (GZCOORD_UNTIL_DELIVERY_DOWN_S) so the case measures it in seconds."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — its scratch and command environment
from gzcoord.carrier import server  # noqa: E402

DOWN_S = 6.0      # the bound after which the watch says the carrier is silent (stderr); it never ends the watch for it
RETRY_S = 0.5


def record() -> dict:
    content = (f"[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nTO: {P.MY_ADDRESS}\n"
               "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000199\nSUBJECT: after-restart\n\nNOTES:\nn\n")
    return {"content": content, "ts": "2026-10-24T12:00:00Z", "seq": None, "message_id": "01a09fc1-0000-7000-8000-000000000199",
            "verdict": "ok", "sender": "x/y"}


class Restart(unittest.TestCase):
    def setUp(self):
        self.env = P.cmd_env(AGENT_FABRIC_SECRET_STORE=P.id_store(),
                             GZCOORD_UNTIL_DELIVERY_DOWN_S=str(DOWN_S), GZCOORD_RETRY_S=str(RETRY_S))
        self.path = server.socket_path(self.env["XDG_RUNTIME_DIR"])
        self.waits = 0
        self.pending: list[dict] = []
        self.carrier = None
        self.up()
        self.addCleanup(self.down)

    def handler(self, req: dict) -> dict:
        if req["op"] == "wait":
            self.waits += 1
            if getattr(self, "hang", False):
                self.release.wait(150)
            # A real carrier holds a wait for tens of seconds. The arm lasts `waited >= wait_total` in NOMINAL slice seconds, so a
            # fake that answers at once would end the arm (which resets the watch's down state) within the case; this one does not.
            time.sleep(1.0)
        recs, self.pending = self.pending, []
        return {"ok": True, "records": recs}

    def up(self) -> None:
        self.carrier = server.Server(self.path, self.handler)

    def down(self) -> None:
        if self.carrier is not None:
            self.carrier.close()
            self.carrier = None

    def restart(self, gap: float) -> None:
        self.down()
        time.sleep(gap)
        self.up()

    def answered_more(self, since: int, within: float = 20.0) -> bool:
        end = time.monotonic() + within
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                return False
            if self.waits >= since + 2:
                return True
            time.sleep(0.05)
        return False

    def start(self) -> None:
        self.proc = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", "6900"], env=self.env, text=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.out: list[str] = []
        self.err: list[str] = []
        for pipe, into in ((self.proc.stdout, self.out), (self.proc.stderr, self.err)):
            threading.Thread(target=lambda p=pipe, i=into: [i.append(x) for x in p], daemon=True).start()
        self.addCleanup(self.stop)
        self.assertTrue(self.answered_more(0), "the watch waits on the carrier: " + "".join(self.err))

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        for pipe in (self.proc.stdout, self.proc.stderr):
            pipe.close()

    def test_a_second_restart_long_after_the_first_does_not_end_the_watch(self):
        self.start()
        self.restart(1.0)
        self.assertTrue(self.answered_more(self.waits), "the watch answers again after the first restart")
        # Longer than the bound while the carrier answers: the first outage is over and must not be counted any more.
        time.sleep(DOWN_S + 2)
        self.assertIsNone(self.proc.poll(), "the watch is still running")
        self.restart(1.0)
        self.assertTrue(self.answered_more(self.waits), "the watch rode out the second restart: " + "".join(self.out + self.err))
        self.assertIsNone(self.proc.poll())
        # The first outage is over: counting the second from its first failure would say the bound at once (j169's reset).
        self.assertNotIn("has not answered", "".join(self.err))
        self.pending.append(record())
        self.assertEqual(self.proc.wait(timeout=30), 0, "".join(self.out + self.err))
        self.assertIn("after-restart", "".join(self.out), "a message listed after the restart is delivered")

    def test_a_carrier_silent_past_the_bound_is_waited_out_and_delivers_when_it_returns(self):
        # 2026-11-18: a carrier silent past the bound ended the watch with exit 5 and the session stayed deaf. The watch now says it
        # on stderr and keeps retrying; the carrier's return delivers the next message without anyone running the watch again.
        self.start()
        self.down()
        end = time.monotonic() + DOWN_S + 20
        while time.monotonic() < end and "has not answered" not in "".join(self.err):
            time.sleep(0.1)
        self.assertIn("has not answered", "".join(self.err), "the bound is said, loudly")
        self.assertIsNone(self.proc.poll(), "the watch did not exit: " + "".join(self.out + self.err))
        self.pending.append(record())
        self.up()
        self.assertEqual(self.proc.wait(timeout=30), 0, "".join(self.out + self.err))
        self.assertIn("after-restart", "".join(self.out), "the message listed after the carrier returned is delivered")

    def test_a_carrier_silent_to_the_deadline_ends_quiet_and_says_why(self):
        # The positive control of the above: the watch is not endless. Past its deadline it ends exit 0, the "run it again" ending.
        self.proc = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", "4"], env=self.env, text=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        self.down()
        out, err = self.proc.communicate(timeout=30)
        self.assertEqual(self.proc.returncode, 0, out + err)
        self.assertIn("is not running", out, "the failure, not the \"waiting for it\" line of a watch that goes on")
        self.assertIn("run the watch again", out)

    def test_a_carrier_that_accepts_and_never_answers_still_says_why_at_the_deadline(self):
        # A hung carrier is not a refusing one: its last arm is cut by the deadline, not by an error, and must not read as an answer.
        # The first arm (55 s asked) times out at 60 s, which is the failure; the second is cut by the deadline, which is no answer.
        self.hang = True
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.proc = subprocess.Popen([P.INBOX_CMD, "--until-delivery", "--deadline", "75"], env=self.env, text=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        out, err = self.proc.communicate(timeout=120)
        self.assertEqual(self.proc.returncode, 0, out + err)
        self.assertIn("run the watch again", out)
        self.assertIn("carrier failed", out)
        self.assertFalse(out.startswith("gzcoord inbox: quiet"), "the failure comes before the quiet line: " + out)

def tearDownModule():
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
