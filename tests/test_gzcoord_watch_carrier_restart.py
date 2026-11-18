#!/usr/bin/env python3
"""A watch in carrier-only rides out carrier restarts (j169). The fleet upgrade restarts interweave-client under every running
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
from gzcoord.transport import mode  # noqa: E402

DOWN_S = 6.0      # the give-up bound the watch is given; a restart below it is ridden out, a silence past it ends the watch
RETRY_S = 0.5


def record() -> dict:
    content = (f"[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nTO: {P.MY_ADDRESS}\n"
               "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000199\nSUBJECT: after-restart\n\nNOTES:\nn\n")
    return {"content": content, "ts": "2026-10-24T12:00:00Z", "seq": None, "message_id": "01a09fc1-0000-7000-8000-000000000199",
            "verdict": "ok", "sender": "x/y"}


class Restart(unittest.TestCase):
    def setUp(self):
        self.env = P.cmd_env(AGENT_FABRIC_SECRET_STORE=P.id_store(), GZCOORD_CHANNEL="fixture:chan",
                             CLAUDE_BRIDGE_URL="http://127.0.0.1:9", CLAUDE_BRIDGE_AUTH_TOKEN="tok",
                             GZCOORD_UNTIL_DELIVERY_DOWN_S=str(DOWN_S), GZCOORD_RETRY_S=str(RETRY_S))
        self.path = server.socket_path(self.env["XDG_RUNTIME_DIR"])
        self.waits = 0
        self.pending: list[dict] = []
        self.carrier = None
        self.up()
        saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
        os.environ["AGENT_FABRIC_STATE_DIR"] = self.env["AGENT_FABRIC_STATE_DIR"]
        try:
            state = os.path.dirname(mode.path())
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = saved
        os.makedirs(state, exist_ok=True)
        mode.write("carrier-only", "h1/op", state)
        self.addCleanup(self.down)

    def handler(self, req: dict) -> dict:
        if req["op"] == "wait":
            self.waits += 1
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
        self.pending.append(record())
        self.assertEqual(self.proc.wait(timeout=30), 0, "".join(self.out + self.err))
        self.assertIn("after-restart", "".join(self.out), "a message listed after the restart is delivered")

    def test_a_carrier_silent_past_the_bound_ends_the_watch_with_exit_5(self):
        # The positive control: the bound is still enforced, counted from the first failure after the carrier's last answer.
        self.start()
        self.down()
        self.assertEqual(self.proc.wait(timeout=DOWN_S + 20), 5, "".join(self.out + self.err))
        self.assertIn("did not answer", "".join(self.out))


def tearDownModule():
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
