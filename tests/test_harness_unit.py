#!/usr/bin/env python3
"""runtime/control/agent-fabric-harness.service: the settings the request names
(Type, Restart, the binary and its session, the condition, the pane step, the
stop that ends claude with SIGTERM) read from the file as systemd reads it.
systemd itself is not run here: the live read-back (docs/live-checks) is the
proof that the unit starts and stops."""
from __future__ import annotations

import configparser
import os
import sys
import tomllib
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import upgrade  # noqa: E402

UNIT = os.path.join(HERE, "runtime", "control", "agent-fabric-harness.service")


def load():
    cp = configparser.RawConfigParser(strict=True, delimiters=("=",), comment_prefixes=("#", ";"), interpolation=None)
    cp.optionxform = str
    with open(UNIT, encoding="utf-8") as fh:
        cp.read_file(fh)
    return cp


class HarnessUnit(unittest.TestCase):
    def setUp(self):
        self.cp = load()

    def test_runs_the_binary_headless_in_the_harness_session(self):
        s = self.cp["Service"]
        self.assertEqual(s["Type"], "simple")
        self.assertEqual(s["ExecStart"].split(), ["/usr/local/bin/agent-fabric-fleetdeck", "--session", "harness", "server"])
        self.assertEqual(s["Restart"], "on-failure")

    def test_an_account_without_the_binary_is_skipped(self):
        self.assertEqual(self.cp["Unit"]["ConditionPathExists"], "/usr/local/bin/agent-fabric-fleetdeck")
        self.assertEqual(self.cp["Unit"]["ConditionPathExists"], self.cp["Service"]["ExecStart"].split()[0])

    def test_the_pane_step_is_the_helper_beside_units_py_run_by_the_pin(self):
        words = self.cp["Service"]["ExecStartPost"].split()
        self.assertEqual(words[0], "/usr/local/bin/fabric-python")
        self.assertEqual(words[1].replace("%h/projects/agent-fabric/", ""), "tools/fabric/control/harness_pane.py")
        self.assertTrue(os.path.isfile(os.path.join(HERE, "tools", "fabric", "control", "harness_pane.py")))
        self.assertEqual(words[2:], ["ensure"])

    def test_the_server_reads_the_fabrics_config_with_the_update_checks_off(self):
        env = dict(a.split("=", 1) for a in self.cp["Service"]["Environment"].split())
        path = env["HERDR_CONFIG_PATH"]
        self.assertTrue(path.startswith("%h/projects/agent-fabric/"))
        with open(os.path.join(HERE, path.replace("%h/projects/agent-fabric/", "")), "rb") as fh:
            config = tomllib.load(fh)
        self.assertEqual(config, {"update": {"version_check": False, "manifest_check": False}})

    def test_a_stop_is_sigterm_to_every_process_and_outlasts_the_sessions_own_stop(self):
        s = self.cp["Service"]
        self.assertEqual((s["KillMode"], s["KillSignal"], s["SendSIGHUP"]), ("control-group", "SIGTERM", "no"))
        self.assertGreater(int(s["TimeoutStopSec"]), upgrade.STOP_WAIT_MS / 1000)

    def test_a_failure_that_survives_restarts_ends_in_failed_not_in_a_loop(self):
        # systemd's default limit (5 in 10 s) never trips at RestartSec=5; the burst must fit the interval at that spacing.
        interval, burst, spacing = int(self.cp["Unit"]["StartLimitIntervalSec"]), int(self.cp["Unit"]["StartLimitBurst"]), int(self.cp["Service"]["RestartSec"])
        self.assertGreaterEqual(burst, 2)
        self.assertGreater(interval, (burst - 1) * spacing)

    def test_it_is_a_user_unit_installed_on_the_default_target(self):
        self.assertEqual(self.cp["Install"]["WantedBy"], "default.target")
        self.assertNotIn("User", self.cp["Service"])    # a user unit runs as its manager's login

    def test_the_sectionless_settings_are_not_hiding_in_a_wrong_section(self):
        self.assertEqual(sorted(self.cp.sections()), ["Install", "Service", "Unit"])


if __name__ == "__main__":
    unittest.main()
