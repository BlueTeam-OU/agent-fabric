#!/usr/bin/env python3
"""tools/fabric/resume.py profile_provider(): under a suite (AGENT_FABRIC_SUITE_RUN, which tests/run.py sets
for every suite it runs) an unset AGENT_FABRIC_RESUME_PROFILES means no profile, never the live routing/profiles.json,
whose agent layer for the login running the suite would change the result (j438, j523)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import resume  # noqa: E402

LOGIN = "zz-unit-login"


class SuiteMarker(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="resume-marker.")
        self.addCleanup(tmp.cleanup)
        # The "live" file: an agent layer for the running login.
        self.live = os.path.join(tmp.name, "profiles.json")
        with open(self.live, "w") as fh:
            json.dump({"version": 1, "agents": {LOGIN: {"launch_provider": "openrouter"}}}, fh)
        patch = mock.patch.object(resume.roots, "routing_profiles", return_value=self.live)
        patch.start()
        self.addCleanup(patch.stop)

    def env(self, **extra: str):
        base = {k: v for k, v in os.environ.items() if k not in (resume.SUITE_MARKER, "AGENT_FABRIC_RESUME_PROFILES")}
        return mock.patch.dict(os.environ, {**base, **extra}, clear=True)

    def test_control_without_marker_reads_the_live_file(self):
        with self.env():
            self.assertEqual(resume.profile_provider(LOGIN, None), "openrouter")

    def test_marker_reads_no_profile(self):
        for marker in ("1", "4"):
            with self.env(**{resume.SUITE_MARKER: marker}):
                self.assertIsNone(resume.profile_provider(LOGIN, None), marker)

    def test_marker_with_empty_fixture_variable_reads_no_profile(self):
        with self.env(**{resume.SUITE_MARKER: "1", "AGENT_FABRIC_RESUME_PROFILES": ""}):
            self.assertIsNone(resume.profile_provider(LOGIN, None))

    def test_marker_does_not_hide_an_explicit_fixture(self):
        with self.env(**{resume.SUITE_MARKER: "1", "AGENT_FABRIC_RESUME_PROFILES": self.live}):
            self.assertEqual(resume.profile_provider(LOGIN, None), "openrouter")


if __name__ == "__main__":
    unittest.main()
