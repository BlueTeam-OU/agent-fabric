#!/usr/bin/env python3
"""tests/run.py run_environment pins FABRIC_CONTROL_CARRIER to "relay": with the committed control_carrier "dual"
(ADR-029 rule 18), an in-process fabric-ctl case would otherwise append its fixture replies to the running account's
real control-arrivals.jsonl and dial its live agentd socket (#583 F1). The dual cases set the variable themselves."""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))

import run  # noqa: E402  tests/run.py
from control import agentd  # noqa: E402


class RunPinsTheRelay(unittest.TestCase):
    def test_the_run_sets_relay_whatever_the_account_exported(self) -> None:
        for outside in ({}, {"FABRIC_CONTROL_CARRIER": "dual"}):
            env = run.run_environment(dict(outside), "/nonexistent-scratch")
            self.assertEqual(env["FABRIC_CONTROL_CARRIER"], "relay", outside)

    def test_the_pin_outranks_a_config_that_says_dual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(HERE, "runtime", "control", "config.json"), encoding="utf-8") as fh:
                committed = json.load(fh)
            dual = os.path.join(tmp, "config.json")
            with open(dual, "w", encoding="utf-8") as fh:
                json.dump({**committed, "control_carrier": agentd.CARRIER_DUAL}, fh)
            self.assertEqual(agentd.control_config({}, dual)["control_carrier"], agentd.CARRIER_DUAL)
            env = run.run_environment({}, "/nonexistent-scratch")
            self.assertEqual(agentd.control_config(env, dual)["control_carrier"], "relay")


class EverySuiteThatRunsCtlPinsItself(unittest.TestCase):
    """A suite run alone (`python3 tests/test_x.py`, the card's way) skips run_environment: each suite that drives
    fabric-ctl in-process sets FABRIC_CONTROL_CARRIER itself, relay or the dual it tests (#583 F1, round 2)."""

    def test_each_in_process_ctl_suite_names_the_carrier(self) -> None:
        drives = re.compile(r"\bctl\.(main|run)\(")
        # Set, not merely named: an assignment into os.environ, or a key of the dict mock.patch.dict lays over
        # os.environ. Any other dict naming the key (a control_config argument, a loop's case) does not count.
        sets = re.compile(r"""os\.environ\[["']FABRIC_CONTROL_CARRIER["']\]\s*="""
                          r"""|mock\.patch\.dict\(\s*os\.environ\s*,\s*\{[^}]*["']FABRIC_CONTROL_CARRIER["']\s*:""")
        found, missing = [], []
        for path in sorted(glob.glob(os.path.join(HERE, "tests", "test_*.py"))):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if drives.search(text):
                found.append(os.path.basename(path))
                if not sets.search(text):
                    missing.append(os.path.basename(path))
        self.assertGreaterEqual(len(found), 9, f"the scan found too few ctl suites to mean anything: {found}")
        self.assertEqual(missing, [], "these suites drive fabric-ctl in-process and do not pin the carrier")


class EverySuiteThatRunsPresenceOrQueuePinsItself(unittest.TestCase):
    """presence.py and queue.py read control_carrier too (W12): a suite that runs them as a subprocess with the
    environment it inherited would dial the live agentd socket under the committed "dual" (j235 review F1)."""

    def test_each_suite_that_spawns_them_pins_the_carrier(self) -> None:
        # The list is the contract: a new suite that spawns presence.py or queue.py is added to it.
        pin = re.compile(r"""os\.environ\[["']FABRIC_CONTROL_CARRIER["']\]\s*=""")
        pinned = [n for n in ("test_presence_cli.py", "test_gzcoord_protocol.py", "test_jobs.py", "test_job_state.py")
                  if pin.search(open(os.path.join(HERE, "tests", n), encoding="utf-8").read())]
        self.assertEqual(pinned, ["test_presence_cli.py", "test_gzcoord_protocol.py", "test_jobs.py", "test_job_state.py"])


if __name__ == "__main__":
    unittest.main()
