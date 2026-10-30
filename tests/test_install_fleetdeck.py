#!/usr/bin/env python3
"""tools/fabric/provisioning/install_fleetdeck.py: the binary copied under a
prefix with its mode, the manifest naming its sha256 and its source, the
refusals that write nothing, and the replacement by rename. Run as the real
command with a minimal environment; the one chown-to-root step is seen
through a mock, since a test is not root."""
from __future__ import annotations

import hashlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "provisioning"))
import install_fleetdeck as ifd  # noqa: E402

SCRIPT = os.path.join(HERE, "tools", "fabric", "provisioning", "install_fleetdeck.py")


def read(path, how="r"):
    with open(path, how) as fh:
        return fh.read()


def mode(path):
    return oct(stat.S_IMODE(os.stat(path).st_mode))[2:]


class InstallFleetdeck(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="ifd-")
        self.addCleanup(__import__("shutil").rmtree, self.t, True)
        self.prefix = os.path.join(self.t, "usr-local")
        self.src = os.path.join(self.t, "built")
        self.write(self.src, b"#!/bin/sh\necho fleetdeck\n", 0o750)

    def write(self, path, data, perm):
        with open(path, "wb") as fh:
            fh.write(data)
        os.chmod(path, perm)

    def run_cmd(self, *argv, prefix=None):
        env = {"PATH": "/usr/bin:/bin", "FLEETDECK_PREFIX": prefix or self.prefix}
        return subprocess.run([sys.executable, "-I", SCRIPT, *argv], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def test_installs_the_binary_0755_and_records_sha256_and_source(self):
        r = self.run_cmd("--from", self.src)
        dst = f"{self.prefix}/bin/agent-fabric-fleetdeck"
        digest = hashlib.sha256(read(self.src, "rb")).hexdigest()
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertEqual(r.stdout, f"agent-fabric-fleetdeck installed to {dst} (sha256 {digest}; manifest: {self.prefix}/share/agent-fabric-fleetdeck/installed.sha256)\n")
        self.assertEqual(read(dst, "rb"), read(self.src, "rb"))
        self.assertEqual(mode(dst), "755")
        self.assertEqual(mode(f"{self.prefix}/bin"), "755")
        man = f"{self.prefix}/share/agent-fabric-fleetdeck/installed.sha256"
        self.assertEqual(read(man), f"{digest}  bin/agent-fabric-fleetdeck\n# source: {self.src}\n")
        self.assertEqual(mode(man), "644")
        c = subprocess.run(["sha256sum", "-c", "--quiet", man], cwd=self.prefix, capture_output=True, text=True, timeout=60)
        self.assertEqual((c.returncode, c.stderr), (0, ""), c.stdout)

    def test_the_manifest_names_the_installed_copy_not_the_source(self):
        # Positive control for the next claim: the digest is of what is at the destination.
        self.run_cmd("--from", self.src)
        self.write(self.src, b"#!/bin/sh\nchanged\n", 0o755)
        dst = f"{self.prefix}/bin/agent-fabric-fleetdeck"
        man = read(f"{self.prefix}/share/agent-fabric-fleetdeck/installed.sha256")
        self.assertIn(hashlib.sha256(read(dst, "rb")).hexdigest(), man)
        self.assertNotIn(hashlib.sha256(read(self.src, "rb")).hexdigest(), man)

    def test_a_rerun_replaces_by_rename_so_a_running_server_keeps_its_inode(self):
        self.run_cmd("--from", self.src)
        dst = f"{self.prefix}/bin/agent-fabric-fleetdeck"
        first = os.stat(dst).st_ino
        held = open(dst, "rb")     # a running server holds the file it started from
        self.addCleanup(held.close)
        os.chmod(dst, 0o600)
        self.write(self.src, b"#!/bin/sh\nnew\n", 0o755)
        r = self.run_cmd("--from", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(mode(dst), "755")
        self.assertEqual(held.read(), b"#!/bin/sh\necho fleetdeck\n")    # the old inode, unchanged
        self.assertNotEqual(os.fstat(held.fileno()).st_ino, os.stat(dst).st_ino)
        self.assertEqual(os.fstat(held.fileno()).st_ino, first)
        self.assertEqual(read(dst, "rb"), b"#!/bin/sh\nnew\n")
        left = [n for n in os.listdir(f"{self.prefix}/bin") + os.listdir(f"{self.prefix}/share/agent-fabric-fleetdeck") if n.startswith(".install-")]
        self.assertEqual(left, [])

    def test_a_source_that_is_not_a_regular_executable_file_is_refused_with_nothing_written(self):
        plain = os.path.join(self.t, "plain")
        self.write(plain, b"data", 0o644)
        link_to_dir = os.path.join(self.t, "linkdir")
        os.symlink(self.t, link_to_dir)
        fifo = os.path.join(self.t, "fifo")
        os.mkfifo(fifo, 0o755)
        for label, path, why in (("a directory", self.t, "not a regular file"), ("a symlink to a directory", link_to_dir, "not a regular file"),
                                 ("a fifo", fifo, "not a regular file"), ("a file without an execute bit", plain, "not executable"),
                                 ("a missing path", os.path.join(self.t, "nowhere"), "No such file")):
            r = self.run_cmd("--from", path)
            self.assertEqual((r.returncode, r.stdout), (1, ""), label)
            self.assertEqual(r.stderr.count("\n"), 1, label)
            self.assertRegex(r.stderr, rf"^install_fleetdeck: .*{why}.*; nothing installed\n$", label)
            self.assertFalse(os.path.exists(self.prefix), label)

    def test_a_symlink_to_an_executable_file_is_followed_as_install_follows_it(self):
        link = os.path.join(self.t, "link")
        os.symlink(self.src, link)
        r = self.run_cmd("--from", link)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.islink(f"{self.prefix}/bin/agent-fabric-fleetdeck"))

    def test_a_prefix_that_cannot_be_made_is_one_line_exit_1_and_no_traceback(self):
        blocked = os.path.join(self.t, "blocked")
        open(blocked, "w").close()
        r = self.run_cmd("--from", self.src, prefix=blocked)
        self.assertEqual((r.returncode, r.stdout), (1, ""))
        self.assertTrue(r.stderr.startswith("install_fleetdeck: ") and r.stderr.count("\n") == 1 and "Traceback" not in r.stderr, r.stderr)

    def test_from_is_required_and_the_default_prefix_is_usr_local(self):
        r = self.run_cmd()
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("--from", r.stderr)
        with mock.patch.object(ifd, "install", return_value="d") as inst, redirect_stdout(io.StringIO()):
            self.assertEqual(ifd.main(["--from", self.src], {}), 0)
        self.assertEqual(inst.call_args.args, ("/usr/local", self.src))
        with mock.patch.object(ifd, "install", return_value="d") as inst, redirect_stdout(io.StringIO()):
            ifd.main(["--from", self.src], {"FLEETDECK_PREFIX": ""})
        self.assertEqual(inst.call_args.args[0], "/usr/local")

    def test_as_root_each_file_is_made_root_owned_before_it_is_in_place(self):
        calls = []
        real_replace = os.replace
        with mock.patch.object(os, "geteuid", return_value=0), \
                mock.patch.object(os, "chown", side_effect=lambda p, u, g: calls.append((os.path.basename(p).startswith(".install-"), u, g))), \
                mock.patch.object(os, "replace", side_effect=lambda a, b: (calls.append("replace"), real_replace(a, b))[1]):
            ifd.install(self.prefix, self.src)
        self.assertEqual(calls, [(True, 0, 0), "replace", (True, 0, 0), "replace"])

    def test_not_root_no_chown_is_attempted(self):
        with mock.patch.object(os, "geteuid", return_value=1000), mock.patch.object(os, "chown", side_effect=AssertionError("chown")):
            ifd.install(self.prefix, self.src)


if __name__ == "__main__":
    unittest.main()
