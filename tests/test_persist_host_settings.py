#!/usr/bin/env python3
"""tools/fabric/provisioning/persist_host_settings.py — the host's reserved ports made from the roster's port_range, and kept across a
reboot the way the platform needs — and `fabric-host <host> persist` running it after persist_accounts.py.

Nothing here reads or writes the host: the proc root, the rc.local.d and sysctl.d directories are scratch ones, the roster is a
copy (or the committed file read-only), the environment of every child is built here. Run as root or not: no case relies on a
permission bit."""
from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import fabric_host  # noqa: E402
from control import carrier_install  # noqa: E402
from provisioning import persist_host_settings as phs  # noqa: E402

SCRIPT = os.path.join(ROOT, "tools", "fabric", "provisioning", "persist_host_settings.py")
LOW, HIGH = carrier_install.roster_port_range(ROOT)      # the committed roster is the one source: no literal here either
RANGE = f"{LOW}-{HIGH}"
LIVE_REL = carrier_install.RESERVED_PORTS_REL


class Case(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="phs-")
        self.addCleanup(shutil.rmtree, self.t, True)
        self.proc, self.rcd, self.sysctld = (os.path.join(self.t, d) for d in ("proc", "rc.local.d", "sysctl.d"))
        self.live = os.path.join(self.proc, LIVE_REL)
        os.makedirs(os.path.dirname(self.live))
        self.set_live("")

    def env(self, platform="fedora-qubes"):
        return {"AGENT_FABRIC_PROC_ROOT": self.proc, "AGENT_FABRIC_RC_LOCAL_D": self.rcd, "AGENT_FABRIC_SYSCTL_D": self.sysctld,
                "AGENT_FABRIC_PLATFORM": platform}

    def set_live(self, text):
        with open(self.live, "w") as fh:
            fh.write(text)

    def get_live(self):
        with open(self.live) as fh:
            return fh.read()

    def go(self, platform="fedora-qubes", root=ROOT):
        with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
            with unittest.mock.patch.object(sys, "stdout", out), unittest.mock.patch.object(sys, "stderr", err):
                rc = phs.run(self.env(platform), root=root)
            out.seek(0)
            err.seek(0)
            return rc, out.read(), err.read()

    @property
    def rc_file(self):
        return os.path.join(self.rcd, phs.RC_NAME)

    @property
    def conf_file(self):
        return os.path.join(self.sysctld, phs.SYSCTL_NAME)

    def roster_root(self, rng):
        root = os.path.join(self.t, "tree")
        os.makedirs(os.path.join(root, "runtime", "interweave"), exist_ok=True)
        with open(os.path.join(root, carrier_install.ROSTER_REL), "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", **({} if rng is None else {"port_range": rng}), "rows": []}, fh)
        return root


class Now(Case):
    def test_an_uncovered_value_gets_the_range_added_and_read_back(self):
        for before, after in (("", RANGE), (f"{LOW}-{HIGH - 1}", RANGE), (f"{LOW + 1}-{HIGH}", RANGE), ("32768", f"32768,{RANGE}"),
                              ("1000-2000,30000", f"1000-2000,30000,{RANGE}"),
                              (f"{LOW + 50}-{LOW + 60}", RANGE)):          # a span inside the range must not shorten it
            self.set_live(before + "\n")
            rc, out, err = self.go()
            self.assertEqual((rc, err, self.get_live()), (0, "", after), before)
            self.assertIn("added", out)

    def test_another_reservation_is_kept_and_a_covered_value_is_left_exactly_as_it_is(self):
        for text in (RANGE, f"{RANGE},50000", f"22,{LOW - 5}-{LOW + 10},{LOW + 11}-{HIGH + 7}", f"{LOW}-{HIGH}\n"):
            self.set_live(text)
            before = os.stat(self.live).st_mtime_ns
            rc, out, err = self.go()
            self.assertEqual((rc, self.get_live(), err), (0, text, ""), text)
            self.assertEqual(os.stat(self.live).st_mtime_ns, before, f"{text!r}: the setting was not written")
            self.assertIn("already covered", out)
        self.set_live("50000")
        self.go()
        self.assertEqual(self.get_live(), f"{RANGE},50000", "positive control: the kept value is a real merge")

    def test_a_value_that_cannot_be_read_is_not_written_over_and_is_a_failure(self):
        for text in ("junk", f"{LOW}-", "1-2,x"):
            self.set_live(text)
            rc, out, err = self.go()
            self.assertEqual((rc, self.get_live()), (1, text), text)
            self.assertIn("cannot be read", err)
            self.assertTrue(os.path.isfile(self.rc_file), "the boot file is still made: it adds to whatever the value is then")
            os.unlink(self.rc_file)
        os.unlink(self.live)
        rc, _, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("persist-host-settings:", err)
        self.assertFalse(os.path.exists(self.live), "nothing was made up where the setting is absent")
        self.set_live("")
        self.assertEqual(self.go()[0], 0, "positive control: a readable value is fine")

    def test_not_covered_after_the_write_is_a_failure(self):
        with unittest.mock.patch.object(phs, "_write_live", lambda *a: None):
            rc, out, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn(f"does not cover {RANGE} after the write", err)
        with unittest.mock.patch.object(phs, "_write_live", side_effect=PermissionError(13, "Permission denied")):
            rc, out, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("could not be set", err)
        self.assertEqual(self.go()[0], 0, "positive control")

    def test_the_range_is_the_rosters_and_nothing_else(self):
        root = self.roster_root([51000, 51009])
        rc, _, _ = self.go(root=root)
        self.assertEqual((rc, self.get_live()), (0, "51000-51009"))
        with open(self.rc_file) as fh:
            body = fh.read()
        self.assertIn("51000-51009", body)
        self.assertNotIn(RANGE, body)
        for bad in (None, [5, 1], [0, 3], [1], "x"):
            self.set_live("32768")
            rc, _, err = self.go(root=self.roster_root(bad))
            self.assertEqual((rc, self.get_live()), (1, "32768"), bad)
            self.assertIn("port_range", err)


class AcrossAReboot(Case):
    def test_a_volatile_root_gets_the_boot_script_and_no_sysctl_file(self):
        rc, out, err = self.go("fedora-qubes")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(stat.S_IMODE(os.stat(self.rc_file).st_mode), 0o755)
        with open(self.rc_file) as fh:
            body = fh.read()
        self.assertEqual(body, phs.rc_script(LOW, HIGH))
        self.assertTrue(body.startswith("#!/bin/sh\n"))
        self.assertFalse(os.path.exists(self.sysctld))
        self.assertEqual(os.listdir(self.rcd), [phs.RC_NAME], "no temporary file is left")

    def test_a_persistent_root_gets_the_sysctl_file_and_no_boot_script(self):
        for platform in ("fedora", "debian", "x-unknown"):
            rc, out, err = self.go(platform)
            self.assertEqual((rc, err), (0, ""), platform)
            self.assertEqual(stat.S_IMODE(os.stat(self.conf_file).st_mode), 0o644)
            with open(self.conf_file) as fh:
                self.assertEqual(fh.read(), phs.sysctl_conf(LOW, HIGH))
            self.assertIn(f"net.ipv4.ip_local_reserved_ports = {RANGE}\n", phs.sysctl_conf(LOW, HIGH))
            self.assertFalse(os.path.exists(self.rcd), platform)
            os.unlink(self.conf_file)

    def test_an_identical_file_is_untouched_a_differing_one_replaced_whole(self):
        self.go()
        first = os.stat(self.rc_file)
        self.assertIn("already as it should be", self.go()[1])
        again = os.stat(self.rc_file)
        self.assertEqual((again.st_ino, again.st_mtime_ns), (first.st_ino, first.st_mtime_ns))
        for hand in ("#!/bin/sh\nsysctl -w net.ipv4.ip_local_reserved_ports=" + RANGE + "\n", ""):
            with open(self.rc_file, "w") as fh:
                fh.write(hand)
            os.chmod(self.rc_file, 0o700)
            rc, out, err = self.go()
            self.assertEqual(rc, 0)
            with open(self.rc_file) as fh:
                self.assertEqual(fh.read(), phs.rc_script(LOW, HIGH), "the owner's hand copy is replaced")
            self.assertEqual(stat.S_IMODE(os.stat(self.rc_file).st_mode), 0o755)
            self.assertIn("written", out)
        os.chmod(self.rc_file, 0o644)
        self.go()
        self.assertEqual(stat.S_IMODE(os.stat(self.rc_file).st_mode), 0o755, "a right content with a wrong mode is not left")

    def test_the_boot_script_adds_the_range_to_the_value_at_boot(self):
        fake_bin = os.path.join(self.t, "bin")
        os.makedirs(fake_bin)
        sysctl = os.path.join(fake_bin, "sysctl")
        record = os.path.join(self.t, "sysctl.args")
        with open(sysctl, "w") as fh:
            fh.write(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}"\n')
        os.chmod(sysctl, 0o755)
        with open(os.path.join(self.t, "script"), "w") as fh:
            fh.write(phs.rc_script(LOW, HIGH).replace("/proc/sys/net/ipv4/ip_local_reserved_ports", self.live))
        for boot, want in (("", f"-w\nnet.ipv4.ip_local_reserved_ports={RANGE}\n"),
                           ("32768\n", f"-w\nnet.ipv4.ip_local_reserved_ports=32768,{RANGE}\n"),
                           ("1000-2000,40000", f"-w\nnet.ipv4.ip_local_reserved_ports=1000-2000,40000,{RANGE}\n")):
            self.set_live(boot)
            r = subprocess.run(["/bin/sh", os.path.join(self.t, "script")], env={"PATH": f"{fake_bin}:/usr/bin:/bin"}, timeout=30,
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.assertEqual((r.returncode, r.stderr), (0, ""), boot)
            with open(record) as fh:
                self.assertEqual(fh.read(), want, boot)
            os.unlink(record)
        os.unlink(self.live)
        r = subprocess.run(["/bin/sh", os.path.join(self.t, "script")], env={"PATH": f"{fake_bin}:/usr/bin:/bin"}, timeout=30,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0, "a value that cannot be read at boot is not written over")
        self.assertFalse(os.path.exists(record))

    def test_a_failed_install_is_counted_and_the_live_setting_is_still_made(self):
        with open(self.rcd, "w") as fh:           # a file where the directory should be
            fh.write("x")
        rc, out, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("could not be installed", err)
        self.assertIn("would not survive a reboot", err)
        self.assertEqual(self.get_live(), RANGE)
        os.unlink(self.rcd)
        self.assertEqual(self.go()[0], 0, "positive control: the same host with a directory there")


class EntryPoint(Case):
    def test_the_real_command_with_a_scratch_environment(self):
        env = {**self.env(), "PATH": "/usr/bin:/bin", "HOME": self.t}
        r = subprocess.run([sys.executable, "-I", SCRIPT], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.get_live(), RANGE)
        self.assertTrue(os.path.isfile(self.rc_file))
        r = subprocess.run([sys.executable, "-I", SCRIPT, "extra"], env=env, capture_output=True, text=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("usage:", r.stderr)


class FabricHostPersist(unittest.TestCase):
    def persist(self, results):
        calls = []

        def step(argv):
            calls.append(argv)
            return results[len(calls) - 1]
        with tempfile.TemporaryDirectory() as t:
            reg = os.path.join(t, "registry.json")
            with open(reg, "w") as fh:
                json.dump({"version": 1, "hosts": {"h1": {"platform": "debian", "ssh": None}},
                           "placement": {"la": "h1", "lb": "h1", "lz": "h2"}}, fh)
            with unittest.mock.patch.object(fabric_host, "resolve_registry", lambda: reg), \
                    unittest.mock.patch.object(fabric_host, "run_hostexec_step", step), \
                    unittest.mock.patch.dict(os.environ, {}):
                rc = fabric_host.main(["h1", "persist"])
        return rc, calls

    def test_both_steps_run_as_root_on_the_pinned_interpreter_the_accounts_first(self):
        rc, calls = self.persist([0, 0])
        base = ["h1", "--", "sudo", "-n", fabric_host.FABRIC_PYTHON, "-I"]
        self.assertEqual((rc, calls), (0, [[*base, "@fabric/tools/fabric/provisioning/persist_accounts.py", "la", "lb"],
                                          [*base, "@fabric/tools/fabric/provisioning/persist_host_settings.py"]]))

    def test_both_always_run_and_the_exit_is_the_worse_of_the_two(self):
        for results, want in (([1, 0], 1), ([0, 1], 1), ([1, 1], 1), ([2, 1], 2), ([0, 126], 126)):
            rc, calls = self.persist(results)
            self.assertEqual((rc, len(calls)), (want, 2), results)

    def test_a_step_runs_as_a_child_with_its_status_a_signals_as_the_shells_and_a_bound(self):
        with tempfile.TemporaryDirectory() as t:
            hx = os.path.join(t, "hx")
            with open(hx, "w") as fh:
                fh.write('#!/bin/sh\ncase "$1" in ok) exit 0;; seven) exit 7;; kill) kill -KILL $$;; hang) sleep 60;; esac\n')
            os.chmod(hx, 0o755)
            with unittest.mock.patch.object(fabric_host, "HX", hx), unittest.mock.patch.object(fabric_host, "PERSIST_TIMEOUT_S", 1), \
                    tempfile.TemporaryFile("w+") as quiet, unittest.mock.patch.object(sys, "stderr", quiet):
                got = {a: fabric_host.run_hostexec_step([a]) for a in ("ok", "seven", "kill", "hang")}
                self.assertEqual(got, {"ok": 0, "seven": 7, "kill": 128 + signal.SIGKILL, "hang": 1})
                with unittest.mock.patch.object(fabric_host, "HX", os.path.join(t, "absent")):
                    self.assertEqual(fabric_host.run_hostexec_step(["ok"]), 127)


if __name__ == "__main__":
    unittest.main()
