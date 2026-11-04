#!/usr/bin/env python3
"""The oracle for projects/gzapp/integration/provisioning/host-check.sh: what
a host must carry for an account that works on gzapp, as the probe the
provisioning worker runs on the account's host for each --project it clones
(tools/fabric/provisioning/worker.py finish: `bash <probe>`, stdin closed,
stdout and stderr merged, status ignored, run only if the file is
executable). The bash script has NO test of its own; these cases are written
from its header and from how the worker calls it, so they pin the contract a
port must keep. The probe is driven through ONE constant, HOST_CHECK (default
the path above; $HOST_CHECK names another entry), run as the worker runs it.

The contract, a test method each:
  test_every_line_is_on_stderr_and_stdout_is_empty — the worker merges the
      streams, so only the order and the text matter to it; a person running
      it by hand sees stdout clean
  test_exit_status_is_zero_whatever_is_missing — "a missing item is named for
      the person, never a stop"
  test_tools_present_are_said_present, test_tools_missing_are_named_missing —
      podman and magick, in that order, found by PATH only
  test_one_line_per_item_in_order — gpg wrapper, podman, magick: three lines,
      each "host-check gzapp: " prefixed, nothing else
  test_gpg_wrapper_line_follows_the_hosts_wrapper — the path is absolute and
      cannot be sandboxed, so the line is asserted against what this host
      has, both forms accepted; the MISSING form names devex-tooling's
      installer so the person knows whom to ask
  test_probe_is_executable_for_the_worker — the worker runs it only if X_OK
  test_a_single_missing_tool_is_named_alone
  test_environment_is_not_read — no variable of the session changes a line

Mutations this fails on (planted on the source as formatted, 2026-10-12; all killed):
  - `exit 0` replaced by the last status: test_exit_status_is_zero_*
  - a missing tool not said (the `||` branch dropped): test_tools_missing_*
  - the tool order swapped: test_one_line_per_item_in_order
  - output moved to stdout: test_every_line_is_on_stderr_*

Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

HOST_CHECK = os.path.abspath(os.environ.get("HOST_CHECK") or os.path.join(
    HERE, "projects", "gzapp", "integration", "provisioning", "host-check.sh"))
if not os.path.isfile(HOST_CHECK):
    sys.exit(f"test: script under test not found at {HOST_CHECK}")

WRAPPER = "/usr/local/bin/ots-git-gpg-wrapper.sh"
PREFIX = "host-check gzapp: "
TIMEOUT_S = 30


class HostCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.bin = tempfile.mkdtemp(prefix="hc.")
        self.addCleanup(shutil.rmtree, self.bin, ignore_errors=True)
        self.bash = shutil.which("bash")
        self.assertIsNotNone(self.bash)

    def fake(self, *tools: str) -> None:
        for t in tools:
            p = os.path.join(self.bin, t)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            os.chmod(p, 0o755)

    def run_probe(self, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        # PATH is the fixture directory alone: the probe finds a tool there or
        # nowhere, so the host's own podman and magick never answer for it.
        env = {"PATH": self.bin, "HOME": self.bin, "LANG": "C.UTF-8", **(extra_env or {})}
        return subprocess.run([self.bash, HOST_CHECK], capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=TIMEOUT_S, check=False)

    def test_every_line_is_on_stderr_and_stdout_is_empty(self) -> None:
        self.fake("podman", "magick")
        p = self.run_probe()
        self.assertEqual(p.stdout, "")
        self.assertEqual(len(p.stderr.splitlines()), 3, p.stderr)

    def test_exit_status_is_zero_whatever_is_missing(self) -> None:
        for tools in ((), ("podman",), ("magick",), ("podman", "magick")):
            with self.subTest(present=tools):
                for t in os.listdir(self.bin):
                    os.remove(os.path.join(self.bin, t))
                self.fake(*tools)
                self.assertEqual(self.run_probe().returncode, 0)

    def test_tools_present_are_said_present(self) -> None:
        self.fake("podman", "magick")
        err = self.run_probe().stderr
        self.assertIn(f"{PREFIX}podman: present\n", err)
        self.assertIn(f"{PREFIX}magick: present\n", err)
        self.assertNotIn("MISSING", err.split("gpg wrapper")[1].split("\n", 1)[1])

    def test_tools_missing_are_named_missing(self) -> None:
        # Positive control for the test above: nothing on PATH, both said missing
        # with the hint a person acts on, and neither said present.
        err = self.run_probe().stderr
        self.assertIn(f"{PREFIX}podman: MISSING (a TemplateVM package on Qubes)\n", err)
        self.assertIn(f"{PREFIX}magick: MISSING (a TemplateVM package on Qubes)\n", err)
        self.assertNotIn("present", err)

    def test_a_single_missing_tool_is_named_alone(self) -> None:
        self.fake("podman")
        err = self.run_probe().stderr
        self.assertIn(f"{PREFIX}podman: present\n", err)
        self.assertIn(f"{PREFIX}magick: MISSING", err)

    def test_one_line_per_item_in_order(self) -> None:
        lines = self.run_probe().stderr.splitlines()
        self.assertEqual(len(lines), 3, lines)
        self.assertTrue(all(l.startswith(PREFIX) for l in lines), lines)
        self.assertEqual([l[len(PREFIX):].split(":")[0] for l in lines], ["gpg wrapper", "podman", "magick"])

    def test_gpg_wrapper_line_follows_the_hosts_wrapper(self) -> None:
        line = self.run_probe().stderr.splitlines()[0]
        if os.access(WRAPPER, os.X_OK) and not os.path.isdir(WRAPPER):
            self.assertEqual(line, f"{PREFIX}gpg wrapper: {WRAPPER}")
        else:
            self.assertTrue(line.startswith(f"{PREFIX}gpg wrapper: MISSING — commit signing needs it"), line)
            self.assertIn("devex-tooling installs it (infra/signing/install-shim.sh)", line)

    def test_run_by_its_bare_name_from_its_own_directory(self) -> None:
        # mutation: the forwarder's `here=.` fallback dropped, so `bash host-check.sh` looked for
        # host-check.sh/host_check.py (#329 F4)
        self.fake("podman", "magick")
        env = {"PATH": self.bin, "HOME": self.bin, "LANG": "C.UTF-8"}
        p = subprocess.run([self.bash, os.path.basename(HOST_CHECK)], capture_output=True, text=True, env=env,
                           cwd=os.path.dirname(HOST_CHECK), stdin=subprocess.DEVNULL, timeout=TIMEOUT_S, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Not a directory", p.stderr)

    def test_probe_is_executable_for_the_worker(self) -> None:
        # worker.py runs the probe only if os.access(X_OK): a lost mode bit is
        # a silently skipped check on every provisioned host.
        if os.environ.get("HOST_CHECK"):
            self.skipTest("a different entry names its own mode")
        self.assertTrue(os.access(HOST_CHECK, os.X_OK), HOST_CHECK)

    def test_environment_is_not_read(self) -> None:
        self.fake("podman")
        plain = self.run_probe().stderr
        noisy = self.run_probe({"AGENT_FABRIC_ROOT": "/nonexistent", "GITHUB_ACTIONS": "true", "CLAUDE_CODE": "1",
                                "PODMAN": "x", "MAGICK": "x"}).stderr
        self.assertEqual(plain, noisy)


if __name__ == "__main__":
    unittest.main()
