#!/usr/bin/env python3
"""The {fix} of every carrier line is told by who reads it (j261): fabric-ctl's carrier ops answer a host's operator only, so an
agent told to run them could do nothing. An operator keeps the commands; anyone else, and a registry that cannot be read, is told
what any login can do."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.transport import carrier  # noqa: E402

ENV = "AGENT_FABRIC_HOSTS_REGISTRY"


class FixByReader(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="j261-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.reg = os.path.join(self.dir, "registry.json")
        with open(self.reg, "w") as fh:
            json.dump({"hosts": {"h1": {"operator": "boss"}, "h2": {}}, "placement": {"agent-a": "h1"}}, fh)
        saved = os.environ.get(ENV)
        os.environ[ENV] = self.reg
        self.addCleanup(lambda: os.environ.pop(ENV, None) if saved is None else os.environ.__setitem__(ENV, saved))
        from gzcoord import gzmsg
        self.t = gzmsg.en()

    def test_operator_gets_the_commands(self):
        for address, login in (("h1/boss", "boss"), ("h2/user", "user")):   # a host with no operator field is user's
            line = carrier.fix_line(self.t, address)
            self.assertIn(f"fabric-ctl {login} interweave says why", line)
            self.assertIn(f"fabric-ctl {login} interweave-start starts it", line)
            self.assertNotIn("OBSERVATION", line)

    def test_non_operator_gets_the_rerun_and_the_coordinator(self):
        for address in ("h1/agent-a", "h1/user", "h3/boss", ""):     # placed agent, another host's operator name, nobody
            line = carrier.fix_line(self.t, address)
            self.assertIn("try again in a few minutes", line)
            self.assertIn("30 s", line)
            self.assertIn("OBSERVATION to fabric-coordinator", line)
            self.assertNotIn("fabric-ctl", line)

    def test_unreadable_registry_is_told_what_anyone_can_do(self):
        # A null host entry: the daemon's own read answers no operator at all (agentd.operator_list), so h2/boss is refused.
        for body in ("", "{", "[]", '{"hosts": 3}', '{"hosts": {"h1": null, "h2": {"operator": "boss"}}}',
                     '{"hosts": {"h2": {"operator": "boss"}, "h1": null}}',     # the null entry after the operator's
                     '{"hosts": {"h2": {"operator": "boss"}}, "x": NaN}',        # the daemon's parser refuses NaN
                     '{"hosts": {"h": {"operator": 12345678901234567890}}}'):   # a number the daemon rounds: h/12345678901234567000
            with open(self.reg, "w") as fh:
                fh.write(body)
            self.assertIn("OBSERVATION", carrier.fix_line(self.t, "h2/boss"), body)
            self.assertIn("OBSERVATION", carrier.fix_line(self.t, "h/12345678901234567890"), body)
        os.remove(self.reg)
        self.assertIn("OBSERVATION", carrier.fix_line(self.t, "h1/boss"))

    def test_a_nesting_too_deep_for_the_parser_is_unreadable(self):
        # Mocked: whether a real 100,000-deep body overflows depends on the interpreter's stack (3.14 may never stop), and a
        # test that passes whether or not the catch exists proves nothing.
        with mock.patch.object(json, "loads", side_effect=RecursionError):
            self.assertIn("OBSERVATION", carrier.fix_line(self.t, "h1/boss"))

    def test_the_gave_up_line_carries_it(self):
        gave = self.t("watch.carrier-gave-up", {"carrier": "InterWeave", "minutes": "10", "fix": carrier.fix_line(self.t, "h1/agent-a")})
        self.assertIn("OBSERVATION to fabric-coordinator", gave)
        gave = self.t("watch.carrier-gave-up", {"carrier": "InterWeave", "minutes": "10", "fix": carrier.fix_line(self.t, "h1/boss")})
        self.assertIn("fabric-ctl boss interweave-start", gave)


if __name__ == "__main__":
    unittest.main()
