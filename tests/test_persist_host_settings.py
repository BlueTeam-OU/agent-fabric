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
import socket
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
HOST = socket.gethostname().split(".")[0]      # the entry's id: what the step asks identity.current_host() for
ROUTE_HEAD = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"

# A firewall-cmd that keeps its zones' port and rich-rule sets in files, answers with firewalld's statuses (0 yes, 1 no, 252 not
# running) and logs every call with the environment it was given. KNOBS: files in the state directory, each a way it misbehaves.
FAKE_FIREWALL_CMD = """#!{python}
import os, sys
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
args = sys.argv[1:]
with open(os.path.join(d, "calls"), "a") as fh:
    fh.write(" ".join(args) + "|" + ",".join(sorted(os.environ)) + "\\n")
def knob(name):
    return os.path.exists(os.path.join(d, name))
perm = "--permanent" in args
zone = next((a.split("=", 1)[1] for a in args if a.startswith("--zone=")), "")
store = os.path.join(d, ("perm" if perm else "live") + "." + zone)
def has(v):
    return os.path.exists(store) and v in open(store).read().splitlines()
for a in args:
    if a == "--state":
        if knob("stopped"):
            sys.stderr.write("not running\\n")
            sys.exit(252)
        print("running")
    elif a.startswith("--get-zone-of-interface="):
        f = os.path.join(d, "zone-of-" + a.split("=", 1)[1])
        if not os.path.exists(f):
            print("no zone")
            sys.exit(2)
        print(open(f).read().strip())
    elif a == "--get-default-zone":
        print("public")
    elif a.startswith(("--query-port=", "--query-rich-rule=")):
        sys.exit(0 if has(a.split("=", 1)[1]) else 1)
    elif a.startswith(("--add-port=", "--add-rich-rule=")):
        if knob("fail-add"):
            sys.stderr.write("Error: COMMAND_FAILED\\n")
            sys.exit(1)
        if not knob("lie"):
            open(store, "a").write(a.split("=", 1)[1] + "\\n")
        print("success")
"""


class Case(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="phs-")
        self.addCleanup(shutil.rmtree, self.t, True)
        self.proc, self.rcd, self.sysctld = (os.path.join(self.t, d) for d in ("proc", "rc.local.d", "sysctl.d"))
        self.live = os.path.join(self.proc, LIVE_REL)
        os.makedirs(os.path.dirname(self.live))
        self.set_live("")
        self.fakebin, self.fw = os.path.join(self.t, "fwbin"), os.path.join(self.t, "fwbin", "state")
        os.makedirs(self.fw)
        self.registry = os.path.join(self.t, "hosts.json")
        self.set_entry({})
        self.set_routes([("eth0", 100)])

    def env(self, platform="fedora-qubes", path=None):
        return {"AGENT_FABRIC_PROC_ROOT": self.proc, "AGENT_FABRIC_RC_LOCAL_D": self.rcd, "AGENT_FABRIC_SYSCTL_D": self.sysctld,
                "AGENT_FABRIC_PLATFORM": platform, "AGENT_FABRIC_HOSTS_REGISTRY": self.registry,
                "PATH": path if path is not None else f"{self.fakebin}:/usr/bin:/bin"}

    def set_entry(self, entry):
        with open(self.registry, "w") as fh:
            json.dump({"version": 1, "hosts": {HOST: entry}, "placement": {}}, fh)

    def set_routes(self, ifaces):
        """(interface, metric) default routes, plus a connected-network row that is not one."""
        os.makedirs(os.path.join(self.proc, "net"), exist_ok=True)
        with open(os.path.join(self.proc, "net", "route"), "w") as fh:
            fh.write(ROUTE_HEAD + "lo\t0000007F\t00000000\t0001\t0\t0\t0\t000000FF\t0\t0\t0\n")
            for name, metric in ifaces:
                fh.write(f"{name}\t00000000\t0100A8C0\t0003\t0\t0\t{metric}\t00000000\t0\t0\t0\n")

    def install_fake_firewall(self):
        path = os.path.join(self.fakebin, "firewall-cmd")
        with open(path, "w") as fh:
            fh.write(FAKE_FIREWALL_CMD.format(python=sys.executable))
        os.chmod(path, 0o755)

    def set_live(self, text):
        with open(self.live, "w") as fh:
            fh.write(text)

    def get_live(self):
        with open(self.live) as fh:
            return fh.read()

    def go(self, platform="fedora-qubes", root=ROOT, path=None):
        with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
            with unittest.mock.patch.object(sys, "stdout", out), unittest.mock.patch.object(sys, "stderr", err):
                rc = phs.run(self.env(platform, path), root=root)
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


class Firewall(Case):
    PORTS = f"{RANGE}/tcp"

    def setUp(self):
        super().setUp()
        self.install_fake_firewall()

    def knob(self, name):
        open(os.path.join(self.fw, name), "w").close()

    def zone_of(self, iface, zone):
        with open(os.path.join(self.fw, f"zone-of-{iface}"), "w") as fh:
            fh.write(zone + "\n")

    def sets(self):
        """{store: lines} of what the fake firewall holds."""
        got = {}
        for n in sorted(os.listdir(self.fw)):
            if n.startswith(("live.", "perm.")):
                with open(os.path.join(self.fw, n)) as fh:
                    got[n] = fh.read().splitlines()
        return got

    def seed(self, store, line):
        with open(os.path.join(self.fw, store), "a") as fh:
            fh.write(line + "\n")

    def calls(self):
        try:
            with open(os.path.join(self.fw, "calls")) as fh:
                return [line.split("|")[0] for line in fh.read().splitlines()]
        except FileNotFoundError:
            return []

    def writes(self):
        return [c for c in self.calls() if "--add-" in c]

    def rule(self, source, ports=None):
        return f'rule family="ipv4" source address="{source}" port port="{ports or RANGE}" protocol="tcp" accept'

    def test_neither_field_is_one_line_and_no_firewall_is_asked(self):
        for path in (None, "/usr/bin:/bin"):               # a host without firewall-cmd is nothing to admit too
            self.set_entry({"platform": "fedora"})
            rc, out, err = self.go(path=path) if path else self.go()
            self.assertEqual((rc, err, self.calls()), (0, "", []), path)
            self.assertEqual([line for line in out.splitlines() if "firewall" in line],
                             ["firewall: neither interweave_address nor interweave_admit: nothing to admit"])

    def test_any_admits_the_roster_range_in_the_zone_of_the_default_route_live_and_permanent_and_reads_it_back(self):
        self.set_routes([("wlan0", 600), ("eth0", 100)])         # the lower metric is the default route
        self.zone_of("eth0", "external")
        self.zone_of("wlan0", "home")
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        rc, out, err = self.go()
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(self.sets(), {f"live.external": [self.PORTS], "perm.external": [self.PORTS]})
        self.assertIn(f"{self.PORTS} admitted in zone external, live and permanent", out)
        calls = self.calls()
        self.assertEqual(calls[0], "--state")
        self.assertEqual(sum("--query-port" in c for c in calls[calls.index(next(c for c in calls if "--add-" in c)):]), 2,
                         "read back, live and permanent, after the writes")
        self.assertFalse([c for c in calls if "rich" in c], "an `any` is a port, not a rule")

    def test_a_zone_the_interface_is_not_in_is_the_default_zone_and_the_child_gets_a_minimal_environment(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.assertEqual(self.go()[0], 0)
        self.assertEqual(sorted(self.sets()), ["live.public", "perm.public"])
        with open(os.path.join(self.fw, "calls")) as fh:
            for line in fh.read().splitlines():
                self.assertEqual(line.split("|")[1], "LC_ALL,PATH", line)

    def test_an_address_or_a_cidr_is_a_rich_rule_limited_to_it_and_never_a_port_for_everyone(self):
        for source in ("203.0.113.7", "203.0.113.0/24", "10.1.2.3/32"):
            for n in os.listdir(self.fw):
                os.unlink(os.path.join(self.fw, n))
            self.set_entry({"interweave_address": "192.168.200.79", "interweave_admit": source})
            rc, out, err = self.go()
            self.assertEqual((rc, err), (0, ""), source)
            self.assertEqual(self.sets(), {"live.public": [self.rule(source)], "perm.public": [self.rule(source)]}, source)
            self.assertFalse([c for c in self.calls() if "--add-port" in c or "--query-port" in c], source)

    def test_a_single_port_range_is_written_as_the_one_port(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.assertEqual(self.go(root=self.roster_root([51000, 51000]))[0], 0)
        self.assertEqual(self.sets()["live.public"], ["51000/tcp"])

    def test_already_admitted_is_one_line_and_no_write_and_half_admitted_writes_only_the_half(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        for store in ("live.public", "perm.public"):
            self.seed(store, self.PORTS)
        rc, out, err = self.go()
        self.assertEqual((rc, err, self.writes()), (0, "", []))
        self.assertIn("already admitted in zone public", out)
        os.unlink(os.path.join(self.fw, "perm.public"))
        rc, out, err = self.go()
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(self.writes(), [f"--permanent --zone=public --add-port={self.PORTS}"], "the live half is not written again")
        self.assertEqual(self.sets()["perm.public"], [self.PORTS])
        self.assertIn("admitted in zone public", out)

    def test_an_earlier_different_range_is_left_and_a_wider_admission_is_not_added_for_an_address(self):
        self.seed("live.public", "40000-40009/tcp")
        self.seed("perm.public", "40000-40009/tcp")
        self.set_entry({"interweave_address": "192.168.200.79", "interweave_admit": "203.0.113.7"})
        self.assertEqual(self.go()[0], 0)
        self.assertEqual(self.sets()["live.public"], ["40000-40009/tcp", self.rule("203.0.113.7")])

    def test_firewalld_not_running_or_absent_is_a_failure_with_nothing_written_and_the_ports_still_reserved(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.knob("stopped")
        rc, out, err = self.go()
        self.assertEqual((rc, self.writes(), self.get_live()), (1, [], RANGE), "the other setting is still made")
        self.assertIn("persist-host-settings: firewall: firewall-cmd --state exited 252: not running", err)
        rc, out, err = self.go(path="/usr/bin:/bin")
        self.assertEqual(rc, 1)
        self.assertIn("firewall-cmd is not installed", err)
        self.assertIn("nftables or iptables only", err)
        os.unlink(os.path.join(self.fw, "stopped"))
        self.assertEqual(self.go()[0], 0, "positive control: the same host with firewalld running")

    def test_a_failing_write_is_a_failure(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.knob("fail-add")
        rc, out, err = self.go()
        self.assertEqual((rc, self.sets()), (1, {}))
        self.assertIn(f"--add-port={self.PORTS} exited 1: Error: COMMAND_FAILED", err)
        os.unlink(os.path.join(self.fw, "fail-add"))
        self.assertEqual(self.go()[0], 0, "positive control")

    def test_a_read_back_that_disagrees_is_a_failure(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.knob("lie")
        rc, out, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn(f"{self.PORTS} is not admitted in zone public live after the write", err)
        self.assertNotIn("admitted in zone public, live and permanent", out)
        os.unlink(os.path.join(self.fw, "lie"))
        self.assertEqual(self.go()[0], 0, "positive control")

    def test_a_field_that_is_not_a_word_of_the_contract_is_a_failure_and_asks_nothing_of_the_firewall(self):
        for entry in ({"interweave_address": "195.69.140.18"}, {"interweave_admit": "everyone"},
                      {"interweave_admit": "10.0.0.1/24"}, {"interweave_admit": "10.0.0.0/33"}, {"interweave_admit": "::/0"},
                      {"interweave_admit": 7}, {"interweave_admit": "ANY"}):
            self.set_entry(entry)
            rc, out, err = self.go()
            self.assertEqual((rc, self.calls()), (1, []), entry)
            self.assertIn("persist-host-settings: firewall:", err, entry)
        self.set_entry({"interweave_address": "195.69.140.18"})
        self.assertIn("interweave_address is set and interweave_admit is not", self.go()[2], "the cause is named, not a type error")
        self.set_entry({"interweave_admit": "10.0.0.0/24"})
        self.assertEqual(self.go()[0], 0, "positive control: an admit alone is a CIDR admission")

    def test_an_unreadable_reserved_ports_value_does_not_stop_the_admission(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        self.set_live("junk")
        rc, out, err = self.go()
        self.assertEqual((rc, self.get_live()), (1, "junk"))
        self.assertIn("cannot be read", err)
        self.assertEqual(self.sets()["perm.public"], [self.PORTS])

    def test_an_entry_or_registry_that_cannot_be_read_and_a_missing_default_route_are_failures(self):
        with open(self.registry, "w") as fh:
            json.dump({"version": 1, "hosts": {"another-host": {}}}, fh)
        rc, _, err = self.go()
        self.assertEqual(rc, 1)
        self.assertIn(f"the entry of host {HOST}", err)
        os.unlink(self.registry)
        self.assertEqual(self.go()[0], 1)
        with open(self.registry, "w") as fh:
            fh.write("{")
        self.assertEqual(self.go()[0], 1)
        self.assertEqual(self.calls(), [])
        self.set_entry({"interweave_admit": "any"})
        self.set_routes([])
        rc, _, err = self.go()
        self.assertEqual((rc, self.writes()), (1, []))
        self.assertIn("has no default route", err)
        os.unlink(os.path.join(self.proc, "net", "route"))
        self.assertEqual(self.go()[0], 1)
        self.set_routes([("eth0", 1)])
        self.assertEqual(self.go()[0], 0, "positive control")

    def test_the_real_command_runs_the_firewall_step_too(self):
        self.set_entry({"interweave_address": "195.69.140.18", "interweave_admit": "any"})
        env = {**self.env(), "HOME": self.t}
        r = subprocess.run([sys.executable, "-I", SCRIPT], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(sorted(self.sets()), ["live.public", "perm.public"])


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
                self.assertEqual(fh.read(), phs.sysctl_conf([(LOW, HIGH)]))
            self.assertIn(f"net.ipv4.ip_local_reserved_ports = {RANGE}\n", phs.sysctl_conf([(LOW, HIGH)]))
            self.assertFalse(os.path.exists(self.rcd), platform)
            os.unlink(self.conf_file)

    def test_the_sysctl_file_carries_every_reservation_since_the_last_file_for_a_key_wins_at_boot(self):
        for live in ("8080", f"8080,{RANGE}", f"{LOW + 5}-{LOW + 9},9000"):
            self.set_live(live)
            self.assertEqual(self.go("fedora")[0], 0, live)
            with open(self.conf_file) as fh:
                body = fh.read()
            self.assertIn(f"= {self.get_live()}\n", body, live)
            self.assertIn("8080" if "8080" in live else "9000", body, live)
            self.assertIn(RANGE, body)
            os.unlink(self.conf_file)

    def test_an_unreadable_value_gets_no_sysctl_file_on_a_persistent_root_and_is_a_failure(self):
        self.set_live("junk")
        rc, out, err = self.go("fedora")
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.conf_file), "a file of the range alone would drop what the value holds")
        self.assertIn("not installed", err)
        self.set_live("")
        self.assertEqual(self.go("fedora")[0], 0, "positive control")
        self.assertTrue(os.path.isfile(self.conf_file))

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


class FabricHostRegistryShape(unittest.TestCase):
    """A registry of the wrong shape is one line and exit 1 on every subcommand that reads it, never a traceback."""

    def run_main(self, doc, argv):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
            reg = os.path.join(t, "registry.json")
            with open(reg, "w") as fh:
                json.dump(doc, fh)
            with unittest.mock.patch.object(fabric_host, "resolve_registry", lambda: reg), \
                    unittest.mock.patch.object(fabric_host, "run_hostexec_step", lambda argv: 0), \
                    unittest.mock.patch.dict(os.environ, {}), \
                    unittest.mock.patch.object(sys, "stdout", out), unittest.mock.patch.object(sys, "stderr", err):
                rc = fabric_host.main(argv)
            out.seek(0)
            err.seek(0)
            return rc, out.read(), err.read()

    def test_a_placement_that_is_not_a_map_of_strings_refuses_persist_and_list(self):
        for placement in (["la"], {"la": ["h1"]}, {"la": None}):
            for argv in (["h1", "persist"], ["list"]):
                rc, out, err = self.run_main({"hosts": {}, "placement": placement}, argv)
                self.assertEqual((rc, out), (1, ""), (placement, argv))
                self.assertTrue(err.startswith("fabric-host: the hosts registry ") and err.endswith(": 'placement' must map each login to a host id\n"), err)
                self.assertEqual(err.count("\n"), 1)

    def test_hosts_that_are_not_a_map_of_objects_refuse(self):
        for hosts in (["h1"], {"h1": "debian"}):
            rc, out, err = self.run_main({"hosts": hosts, "placement": {}}, ["list"])
            self.assertEqual((rc, out), (1, ""), hosts)
            self.assertIn("'hosts' must map each host id to an object", err)

    def test_list_names_the_host_that_lacks_a_platform_or_operator(self):
        rc, out, err = self.run_main({"hosts": {"h1": {"operator": "op"}}, "placement": {}}, ["list"])
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("host h1 has no 'platform'", err)
        rc, out, err = self.run_main({"hosts": {"h1": {"platform": "debian", "operator": "op", "ssh": None}}, "placement": {"la": "h1"}}, ["list"])
        self.assertEqual((rc, err), (0, ""), "positive control: a well-formed registry lists")
        self.assertIn("accounts: la", out)


class FabricHostPersist(unittest.TestCase):
    def persist(self, results, host="h1"):
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
                rc = fabric_host.main([host, "persist"])
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

    def test_with_no_placements_only_the_settings_step_runs_and_its_exit_is_the_exit(self):
        base = ["h3", "--", "sudo", "-n", fabric_host.FABRIC_PYTHON, "-I"]
        for result in (0, 1, 126):
            with tempfile.TemporaryFile("w+") as err, unittest.mock.patch.object(sys, "stderr", err):
                rc, calls = self.persist([result], host="h3")
                err.seek(0)
                said = err.read()
            self.assertEqual((rc, calls), (result, [[*base, "@fabric/tools/fabric/provisioning/persist_host_settings.py"]]))
            self.assertEqual(said, "fabric-host: no placements on h3: persist_accounts.py skipped, persist_host_settings.py runs\n")

    def test_with_placements_the_skip_line_is_not_said(self):
        with tempfile.TemporaryFile("w+") as err, unittest.mock.patch.object(sys, "stderr", err):
            self.persist([0, 0])
            err.seek(0)
            self.assertEqual(err.read(), "")

    def test_a_step_runs_as_a_child_with_its_status_a_signals_as_the_shells_and_a_bound(self):
        with tempfile.TemporaryDirectory() as t:
            hx = os.path.join(t, "hx")
            with open(hx, "w") as fh:
                fh.write('#!/bin/sh\ncase "$1" in ok) exit 0;; seven) exit 7;; kill) kill -KILL $$;; hang) exec sleep 60;; esac\n')
            os.chmod(hx, 0o755)
            with unittest.mock.patch.object(fabric_host, "HX", hx), unittest.mock.patch.object(fabric_host, "PERSIST_TIMEOUT_S", 1), \
                    tempfile.TemporaryFile("w+") as quiet, unittest.mock.patch.object(sys, "stderr", quiet):
                got = {a: fabric_host.run_hostexec_step([a]) for a in ("ok", "seven", "kill", "hang")}
                self.assertEqual(got, {"ok": 0, "seven": 7, "kill": 128 + signal.SIGKILL, "hang": 1})
                with unittest.mock.patch.object(fabric_host, "HX", os.path.join(t, "absent")):
                    self.assertEqual(fabric_host.run_hostexec_step(["ok"]), 127)


if __name__ == "__main__":
    unittest.main()
