#!/usr/bin/env python3
"""The three shell readers of the hosts registry (both completions and ssh-operator.sh) resolve it as
tools/fabric/roots.py hosts_registry() will after the operator's data leaves the engine (agent-fabric
docs/split/move-plan.md §3, step A): AGENT_FABRIC_HOSTS_REGISTRY, then AGENT_FABRIC_OPERATOR, then the operator's clone
<home>/projects/blueteam-fabric when it exists, then the engine root. Each tree here places a login of its own on
the host, so the login that comes back names the tree that was read, and the first tree that applies wins even
when a later one has a registry too. A registry that resolves to no file is said and never read from a later tree
(the positive control for that is the same shell with the file present)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVETO = os.path.join(HERE, "runtime", "provisioning", "moveto", "completion.bash")
CTL = os.path.join(HERE, "tools", "fabric", "control", "completion.bash")
HOST = "here"
OPKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGb1y2fxD0RkCq3dHn2iN8f3mR1vD0n1QvJx2v0r2X7a"
SOURCES = ("override", "operator", "clone", "engine")


def login(source: str) -> str:
    return f"from-{source}"


class Resolution(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="hostsreg-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, "home")
        self.trees = {
            "operator": os.path.join(self.tmp, "op"),
            "clone": os.path.join(self.home, "projects", "blueteam-fabric"),
            # Beside the clone: ssh-operator.sh looks for the clone next to its own checkout, the completions in the login's home.
            "engine": os.path.join(self.home, "projects", "agent-fabric"),
        }
        self.override = os.path.join(self.tmp, "reg-override.json")
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        # The host name is the fixture's, not the machine's; moveto's completion falls back to `moveto --list` when
        # the registry gives nothing, which must not find the tool of whoever runs the suite.
        self.stub("hostname", f"echo {HOST}")
        self.stub("moveto", "exit 0")
        # The login's home comes from the passwd database, not from $HOME: the stub is the database, and $HOME is
        # somewhere else on purpose, with a clone in it that must never be taken.
        self.stub("getent", f'echo "fixture:x:1000:1000::{self.home}:/bin/bash"')
        self.session_home = os.path.join(self.tmp, "session-home")
        os.makedirs(os.path.join(self.session_home, "projects", "blueteam-fabric", "runtime", "hosts"))
        with open(os.path.join(self.session_home, "projects", "blueteam-fabric", "runtime", "hosts", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "hosts": {}, "placement": {"from-session-home": HOST}}, fh)
        self.base = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": self.session_home, "LC_ALL": "C"}

    def stub(self, name: str, body: str) -> None:
        path = os.path.join(self.tmp, "bin", name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\n{body}\n")
        os.chmod(path, 0o755)

    def have(self, *sources: str) -> None:
        for source in sources:
            path = self.override if source == "override" else os.path.join(self.trees[source], "runtime", "hosts", "registry.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "hosts": {}, "placement": {login(source): HOST}}, fh)

    def env(self, **extra: str) -> dict[str, str]:
        return {**self.base, "AGENT_FABRIC_ROOT": self.trees["engine"], **extra}

    # Each reader: the logins it read from the registry, and its stderr.
    def moveto(self, env: dict[str, str]) -> tuple[list[str], str]:
        r = subprocess.run(["bash", "-c", 'source "$1"; _moveto_accounts', "_", MOVETO], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split(), r.stderr

    def ctl(self, env: dict[str, str]) -> tuple[list[str], str]:
        r = subprocess.run(["bash", "-c", 'source "$1"; _fabric_ctl_logins', "_", CTL], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split(), r.stderr

    def ssh(self, env: dict[str, str]) -> tuple[list[str], str]:
        enter = os.path.join(self.tmp, "enter")
        with open(enter, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(enter, 0o755)
        pub = os.path.join(self.tmp, "op.pub")
        with open(pub, "w", encoding="utf-8") as fh:
            fh.write(OPKEY + " owner@deck\n")
        env = {**env, "AGENT_FABRIC_SSH_HOST": HOST, "AGENT_FABRIC_SSH_STAGE": os.path.join(self.tmp, "stage"),
               "AGENT_FABRIC_RC_LOCAL": os.path.join(self.tmp, "rc.local"), "AGENT_FABRIC_PLATFORM": "fedora-qubes",
               "AGENT_FABRIC_MOVETO_ENTER": enter}
        r = subprocess.run(["bash", self.ssh_script(), "--dry-run", pub], env=env, capture_output=True, text=True, timeout=60)
        # The fixture's logins have no accounts, which the script warns about; only its words on the registry count.
        said = "".join(line + "\n" for line in r.stderr.splitlines() if "no hosts registry" in line)
        if r.returncode != 0:
            return [], said
        return [login(s) for s in SOURCES if login(s) in r.stdout], said

    def ssh_script(self) -> str:
        """The script as the engine fixture's own copy: its engine root is the checkout it sits in, not AGENT_FABRIC_ROOT."""
        copies = (("runtime/provisioning/platform/qubes/ssh-operator.sh", 0o755), ("runtime/provisioning/platform/qubes/ssh-restore.sh", 0o755),
                  ("runtime/provisioning/platform/detect.sh", 0o644), ("runtime/provisioning/moveto/enter-ssh", 0o755))
        for rel, mode in copies:
            dest = os.path.join(self.trees["engine"], rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(os.path.join(HERE, rel), dest)
            os.chmod(dest, mode)
        return os.path.join(self.trees["engine"], copies[0][0])

    def each(self):
        for name in ("moveto", "ctl", "ssh"):
            yield name, getattr(self, name)

    def test_the_first_of_the_four_that_applies_wins_though_the_later_ones_have_a_registry_too(self):
        self.have(*SOURCES)
        cases = (
            ({"AGENT_FABRIC_HOSTS_REGISTRY": self.override, "AGENT_FABRIC_OPERATOR": self.trees["operator"]}, "override"),
            ({"AGENT_FABRIC_OPERATOR": self.trees["operator"]}, "operator"),
            ({}, "clone"),
        )
        for name, read in self.each():
            for extra, want in cases:
                with self.subTest(reader=name, expect=want):
                    self.assertEqual(read(self.env(**extra)), ([login(want)], ""))

    def test_with_no_operator_and_no_clone_the_engine_root_is_read(self):
        self.have("engine")
        for name, read in self.each():
            with self.subTest(reader=name):
                self.assertEqual(read(self.env()), ([login("engine")], ""))

    def test_empty_variables_count_as_unset(self):
        self.have("clone", "engine")
        for name, read in self.each():
            with self.subTest(reader=name):
                got = read(self.env(AGENT_FABRIC_HOSTS_REGISTRY="", AGENT_FABRIC_OPERATOR=""))
                self.assertEqual(got, ([login("clone")], ""))

    def test_the_sessions_home_is_never_read_for_the_clone(self):
        # self.session_home holds a clone with its own registry; neither it nor $HOME's engine default may answer.
        self.have("engine")
        for name, read in self.each():
            with self.subTest(reader=name):
                logins, _ = read(self.env())
                self.assertEqual(logins, [login("engine")])

    def test_an_operator_clone_that_is_not_a_directory_is_not_taken(self):
        self.have("engine")
        os.makedirs(os.path.dirname(self.trees["clone"]), exist_ok=True)
        with open(self.trees["clone"], "w", encoding="utf-8") as fh:
            fh.write("a file, not a clone\n")
        for name, read in self.each():
            with self.subTest(reader=name):
                self.assertEqual(read(self.env()), ([login("engine")], ""))

    def test_a_registry_missing_from_the_chosen_tree_is_said_and_the_next_tree_is_not_read(self):
        self.have("engine")   # present, and never to be read in its place
        for extra, where in (
            ({"AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(self.tmp, "nope.json")}, os.path.join(self.tmp, "nope.json")),
            ({"AGENT_FABRIC_OPERATOR": self.trees["operator"]}, os.path.join(self.trees["operator"], "runtime", "hosts", "registry.json")),
        ):
            for name, read in self.each():
                with self.subTest(reader=name, where=where):
                    logins, err = read(self.env(**extra))
                    self.assertEqual(logins, [])
                    self.assertIn("no hosts registry at " + where, err)
        os.makedirs(self.trees["clone"])      # a clone with no registry in it
        for name, read in self.each():
            with self.subTest(reader=name, where="clone"):
                logins, err = read(self.env())
                self.assertEqual(logins, [])
                self.assertIn("no hosts registry at " + os.path.join(self.trees["clone"], "runtime", "hosts", "registry.json"), err)

    def test_a_missing_engine_registry_is_said(self):
        for name, read in self.each():
            with self.subTest(reader=name):
                logins, err = read(self.env())
                self.assertEqual(logins, [])
                self.assertIn("no hosts registry at " + os.path.join(self.trees["engine"], "runtime", "hosts", "registry.json"), err)

    def test_ssh_operator_refuses_with_exit_1_when_there_is_no_registry(self):
        # The registry used to reach python3 as a missing file and end in a traceback; the exit code is the contract.
        enter = os.path.join(self.tmp, "enter")
        with open(enter, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(enter, 0o755)
        pub = os.path.join(self.tmp, "op.pub")
        with open(pub, "w", encoding="utf-8") as fh:
            fh.write(OPKEY + "\n")
        env = {**self.env(), "AGENT_FABRIC_SSH_HOST": HOST, "AGENT_FABRIC_MOVETO_ENTER": enter, "AGENT_FABRIC_PLATFORM": "fedora-qubes"}
        r = subprocess.run(["bash", self.ssh_script(), "--dry-run", pub], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
