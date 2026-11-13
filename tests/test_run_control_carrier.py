#!/usr/bin/env python3
"""tests/run.py run_environment pins FABRIC_CONTROL_CARRIER to "relay": with the committed control_carrier "dual"
(ADR-029 rule 18), an in-process fabric-ctl case would otherwise append its fixture replies to the running account's
real control-arrivals.jsonl and dial its live agentd socket (#583 F1). The dual cases set the variable themselves."""
from __future__ import annotations

import os
import sys
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

    def test_the_pin_outranks_the_committed_file(self) -> None:
        env = run.run_environment({}, "/nonexistent-scratch")
        self.assertEqual(agentd.control_config(env)["control_carrier"], "relay")
        self.assertEqual(agentd.control_config({})["control_carrier"], agentd.CARRIER_DUAL,
                         "the committed file is dual: without the pin a suite would run on it")


if __name__ == "__main__":
    unittest.main()
