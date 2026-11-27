#!/usr/bin/env python3
"""Every site in inbox.py that says a carrier failure hands `explain` the login's own printer (review 799217cd of #652): a
caller that drops it prints the line in English to a holder whose locale has a dictionary, and nothing else fails. The real inbox
runs in a child whose printer wraps each key as «key», against no carrier at all (a runtime directory with no socket); the
English line has no «, so a dropped printer is the only way the marker is missing. The old relay-refusal cases (401, exit 4,
--replay by relay seq) went with the relay: a replay is the journal's and never fails on a transport."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_protocol as P  # noqa: E402 — its scratch and command environment

# The printer is replaced where inbox reads it: i18n.t_for is called once per run, before any line is said.
DRIVER = ("import sys; sys.path.insert(0, sys.argv[1])\n"
          "from gzcoord import i18n, inbox\n"
          "i18n.t_for = lambda me, **o: (lambda key, vars=None: '\\u00ab' + key + '\\u00bb')\n"
          "sys.exit(inbox.run(sys.argv[2:]))\n")


def tearDownModule():
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)


class ExplainPrinter(unittest.TestCase):
    def run_inbox(self, *argv: str) -> subprocess.CompletedProcess:
        env = P.cmd_env(AGENT_FABRIC_SECRET_STORE=P.id_store(), GZCOORD_UNTIL_DELIVERY_DOWN_S="3", GZCOORD_RETRY_S="1")
        return subprocess.run([sys.executable, "-c", DRIVER, P.TOOLS, *argv], env=env, capture_output=True, text=True,
                              timeout=120, stdin=subprocess.DEVNULL)

    def test_the_positive_control_a_watch_with_no_carrier_ends_quiet_at_its_deadline(self):
        r = self.run_inbox("--until-delivery", "--deadline", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_watch_arm_says_the_failure_in_the_logins_printer(self):
        r = self.run_inbox("--until-delivery", "--deadline", "3")
        self.assertIn("«transport.carrier-absent»", r.stdout, r.stdout + r.stderr)

    def test_a_wait_says_the_failure_in_the_logins_printer(self):
        r = self.run_inbox("--wait", "1")
        self.assertIn("«transport.carrier-absent»", r.stderr, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
