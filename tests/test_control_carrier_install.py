#!/usr/bin/env python3
"""Tests for tools/fabric/control/carrier_install.py: the `interweave-install` action and the `interweave` read
(agent-fabric ADR-064 §5 rule 4). The release is an archive built here with the layout of the real one
(<root>/bin, <root>/systemd, <root>/install.sh) whose install.sh does what the real one does to HOME; the
download is a fake that writes it (a real local HTTP server where the size bound is the subject). Nothing reaches
the network and nothing is installed outside the scratch directories."""
from __future__ import annotations

import fcntl
import hashlib
import http.server
import io
import json
import os
import shutil
import stat
import sys
import tarfile
import subprocess
import tempfile
import threading
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from control import agentd, carrier_install as iw, ctl, ops  # noqa: E402
from control.sign import ACTION_OPS  # noqa: E402

VERSION = "0.1.0"
ROOT = f"interweave-{VERSION}-x86_64-unknown-linux-gnu"
TOKEN = "ghs_SECRETVALUE0123456789"
PROGRAMS = ("transport-daemon", "transportctl", "human-desktop", "interweave-human")
REPORTS = {"transportctl": f"transportctl {VERSION}+abcdef123456", "transport-daemon": f"transport-daemon {VERSION}+abcdef123456"}
UNITS = ("interweave-daemon@.service", "interweave-client@.service")


def program(name: str, line: str | None = None, extra: str = "", code: int | None = None) -> bytes:
    # The real archive carries desktop programs that have no --version contract (human-desktop exits 1 under it):
    # only the pin's `reports` are asked, and the read must not depend on the others.
    if code is None:
        code = 0 if name in REPORTS else 1
    line = REPORTS.get(name, f"{name} {VERSION}") if line is None else line
    return f"#!/bin/sh\n{extra}\nprintf '%s\\n' '{line}'\nexit {code}\n".encode()


# What the real install.sh does to HOME (programs by temporary name then rename, units, nothing enabled), without
# the checks and the systemctl call the real one adds.
def install_sh(extra: str = "", code: int = 0, after: str = "") -> bytes:
    return f"""#!/bin/sh
set -eu
{extra}
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/.local/bin" "${{XDG_CONFIG_HOME:-$HOME/.config}}/systemd/user"
for exe in {" ".join(PROGRAMS)}; do
    cp "$here/bin/$exe" "$HOME/.local/bin/.$exe.install"
    mv -f "$HOME/.local/bin/.$exe.install" "$HOME/.local/bin/$exe"
done
for unit in {" ".join(UNITS)}; do
    cp "$here/systemd/$unit" "${{XDG_CONFIG_HOME:-$HOME/.config}}/systemd/user/$unit"
done
{after}
exit {code}
""".encode()


def default_members(over: dict | None = None) -> list[tuple[str, bytes, str]]:
    """(name, content, kind): kind "file", "exec" (a file with the execute bit), "dir", "link" (content = target)."""
    m: dict[str, tuple[bytes, str]] = {f"{ROOT}/bin/{n}": (program(n), "exec") for n in PROGRAMS}
    m.update({f"{ROOT}/systemd/{u}": (b"[Unit]\n", "file") for u in UNITS})
    m[f"{ROOT}/install.sh"] = (install_sh(), "exec")
    m[f"{ROOT}/README.md"] = (b"readme\n", "file")
    for k, v in (over or {}).items():
        m[f"{ROOT}/{k}"] = v
    out: list[tuple[str, bytes, str]] = [(ROOT, b"", "dir"), (f"{ROOT}/bin", b"", "dir"), (f"{ROOT}/systemd", b"", "dir")]
    out += [(n, c, k) for n, (c, k) in m.items()]
    return out


def tarball(members: list[tuple[str, bytes, str]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tf.addfile(info)
            elif kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, content.decode()
                tf.addfile(info)
            elif kind == "hardlink":
                info.type, info.linkname = tarfile.LNKTYPE, content.decode()
                tf.addfile(info)
            elif kind == "device":
                info.type, info.devmajor, info.devminor = tarfile.CHRTYPE, 1, 3
                tf.addfile(info)
            else:
                info.size, info.mode = len(content), 0o755 if kind == "exec" else 0o644
                tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def pin_for(artifact: bytes, **over) -> dict:
    b = {"url": "https://api.github.com/repos/o/r/releases/assets/1", "name": f"{ROOT}.tar.gz", "size": len(artifact),
         "sha256": hashlib.sha256(artifact).hexdigest(), "root": ROOT, "reports": REPORTS, **over}
    return {"version": 1, "description": "fixture", "current": VERSION,
            "releases": {VERSION: {"tag": f"v{VERSION}", "commit": "a" * 40, "release_run": "run 1", "x86_64": b}}}


def rd(path: str) -> str:
    with open(path) as fh:
        return fh.read()


def digest_of(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Systemd:
    """The user manager and the carrier's status command, as the module's `run` sees them; every other command really runs.
    states: unit -> ActiveState (missing = inactive); manager=False: no user manager (systemctl cannot connect)."""

    def __init__(self):
        self.states: dict[str, str] = {}
        self.manager = True
        self.restarts: list[str] = []
        self.restart_rc: dict[str, int] = {}
        self.after_restart: dict[str, str] = {}        # unit -> the state it is in once restarted (default active)
        self.status_rcs: list[int] = [0]               # one per `status` call; the last repeats
        self.status_calls = 0
        self.hang: str | None = None                   # "show" | "restart" | "status": that command times out
        self.on_restart = None                         # called with the unit, to change something else
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kw):
        name = os.path.basename(argv[0])
        if name not in ("systemctl", "gzcoord-carrier"):
            return subprocess.run(argv, **kw)
        self.calls.append(list(argv))
        done = lambda rc=0, out="": subprocess.CompletedProcess(argv, rc, out, "")   # noqa: E731
        if name == "gzcoord-carrier":
            if self.hang == "status":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            rc = self.status_rcs[min(self.status_calls, len(self.status_rcs) - 1)]
            self.status_calls += 1
            return done(rc, "{}\n" if rc == 0 else "")
        if not self.manager:
            raise FileNotFoundError("systemctl")
        verb = argv[2]
        if verb == "show":
            if self.hang == "show":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return done(0, self.states.get(argv[-1], "inactive") + "\n")
        if self.hang == "restart":
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        unit = argv[-1]
        self.restarts.append(unit)
        if self.on_restart:
            self.on_restart(unit)
        if self.restart_rc.get(unit):
            return done(self.restart_rc[unit])
        self.states[unit] = self.after_restart.get(unit, "active")
        return done()


DAEMON_UNIT, CLIENT_UNIT = "interweave-daemon@gzcoord.service", "interweave-client@gzcoord.service"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="test_control_carrier_install.")
        self.addCleanup(self._tmp.cleanup)
        t = self._tmp.name
        self.root, self.home, self.state = (os.path.join(t, n) for n in ("root", "home", "state"))
        for d in (os.path.join(self.root, "runtime", "interweave"), self.home):
            os.makedirs(d)
        with open(os.path.join(self.root, iw.ROSTER_REL), "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199], "rows": []}, fh)
        self.systemd = Systemd()
        self.fetched: list[tuple[str, str, dict]] = []
        self.sentinel = os.path.join(t, "ran")
        env = {"XDG_CONFIG_HOME": "", "XDG_RUNTIME_DIR": "", "DBUS_SESSION_BUS_ADDRESS": ""}
        patcher = unittest.mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for k in env:
            os.environ.pop(k)

    def release(self, members=None, pin_over=None, artifact: bytes | None = None) -> bytes:
        """Writes the pin and decides the artifact the fake download delivers."""
        art = artifact if artifact is not None else tarball(members if members is not None else default_members())
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin_for(art, **(pin_over or {})), fh)
        self.artifact = art
        return art

    def fetch(self, url, token, dest, **k):
        self.fetched.append((url, token, k))
        with open(dest, "wb") as fh:
            fh.write(self.artifact)
        return len(self.artifact), hashlib.sha256(self.artifact).hexdigest()

    def install(self, request=None, **kw):
        opts = dict(root=self.root, home=self.home, state=self.state, fetch=self.fetch, token=lambda name: TOKEN, machine="x86_64",
                    run=self.systemd, sleep=lambda s: None)
        opts.update(kw)
        return iw.carrier_install({} if request is None else request, **opts)

    @property
    def bindir(self):
        return iw.bin_dir(self.home)

    def installed_names(self) -> list[str]:
        return sorted(os.listdir(self.bindir)) if os.path.isdir(self.bindir) else []

    def nothing_installed(self, why=""):
        self.assertEqual(self.installed_names(), [], why)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config")), why)
        self.assertIsNone(iw.read_marker(self.state), why)
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)), f"the temporary directory is gone {why}")
        self.assertFalse(os.path.exists(self.sentinel), f"nothing was executed {why}")


class Pin(unittest.TestCase):
    def test_the_committed_pin_has_the_shape_the_action_relies_on(self):
        with open(os.path.join(HERE, iw.PIN_REL)) as fh:
            pin = json.load(fh)
        self.assertIsNone(iw.pin_problem(pin))
        self.assertEqual(iw.load_pin(HERE)["version"], 1)
        for arch in ("x86_64",):
            self.assertIn(arch, pin["releases"][pin["current"]], "the pinned release has the build this fleet runs")

    def test_a_pin_that_breaks_the_shape_is_refused_one_defect_at_a_time(self):
        good = pin_for(b"x")
        self.assertIsNone(iw.pin_problem(good), "positive control")
        rel = lambda d: d["releases"][VERSION]  # noqa: E731
        b = lambda d: rel(d)["x86_64"]  # noqa: E731
        cases = {
            "not version 1": lambda d: d.update(version=2),
            "no releases": lambda d: d.update(releases={}),
            "a current that is no release": lambda d: d.update(current="9.9.9"),
            "no current": lambda d: d.pop("current"),
            "a release that is no version": lambda d: d["releases"].update({"latest": d["releases"].pop(VERSION)}),
            "a tag of another version": lambda d: rel(d).update(tag="v9.9.9"),
            "a short commit": lambda d: rel(d).update(commit="abc"),
            "no build": lambda d: rel(d).pop("x86_64"),
            "an http url": lambda d: b(d).update(url="http://api.github.com/x"),
            "a name that is no tarball": lambda d: b(d).update(name="x.zip"),
            "a name with a path": lambda d: b(d).update(name="a/b.tar.gz"),
            "no size": lambda d: b(d).pop("size"),
            "a size of zero": lambda d: b(d).update(size=0),
            "a boolean size": lambda d: b(d).update(size=True),
            "a short digest": lambda d: b(d).update(sha256="ab" * 31),
            "an upper-case digest": lambda d: b(d).update(sha256="AB" * 32),
            "a root with a path": lambda d: b(d).update(root="a/b"),
            "a root that climbs": lambda d: b(d).update(root=".."),
            "no reports": lambda d: b(d).pop("reports"),
            "empty reports": lambda d: b(d).update(reports={}),
            "a program with a path": lambda d: b(d).update(reports={"../x": "x 1"}),
            "a value that is no string": lambda d: b(d).update(reports={"transportctl": 1}),
        }
        for label, mutate in cases.items():
            d = json.loads(json.dumps(good))
            mutate(d)
            self.assertIsNotNone(iw.pin_problem(d), label)

    def test_a_pin_that_cannot_be_read_is_one_line_never_a_default(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(iw.PinError, "cannot be read"):
                iw.load_pin(root)
            os.makedirs(os.path.join(root, "runtime", "interweave"))
            with open(os.path.join(root, iw.PIN_REL), "w") as fh:
                fh.write("{")
            with self.assertRaisesRegex(iw.PinError, "is not JSON"):
                iw.load_pin(root)


class Refusals(Case):
    def test_the_request_has_no_arguments_at_all(self):
        self.release()
        for args in ({"version": VERSION}, {"url": "https://x"}, {"sha256": "0" * 64}, {"path": "/tmp/x"}, [VERSION], "x", 0):
            r = iw.carrier_install({"args": args}, root=self.root, home=self.home, state=self.state, fetch=self.fetch,
                                      token=lambda n: TOKEN, machine="x86_64")
            self.assertEqual(r["status"], "refused", args)
            self.assertIn("takes no argument", r["reason"], args)
        self.assertEqual(self.fetched, [])
        for ok in ({}, {"args": None}, {"args": {}}):
            self.nothing_installed("before the controls")
            self.assertEqual(self.install(ok)["status"], "installed", f"positive control {ok}")
            shutil.rmtree(self.home)
            shutil.rmtree(self.state)
            os.makedirs(self.home)

    def test_an_architecture_the_pin_has_no_build_for_is_refused(self):
        self.release()
        r = self.install(machine="armv7l")
        self.assertEqual((r["status"], r["reason"]), ("refused", "the reviewed pin has no 0.1.0 build for armv7l"))
        self.assertEqual(self.install(machine="amd64")["status"], "installed", "amd64 is x86_64")

    def test_a_missing_pin_is_a_failure_that_says_so(self):
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("cannot be read", r["reason"])

    def test_no_token_means_no_download(self):
        self.release()
        r = self.install(token=lambda name: None)
        self.assertEqual(r["status"], "failed")
        self.assertIn("no GH_TOKEN", r["reason"])
        self.assertEqual(self.fetched, [])
        self.nothing_installed()

    def test_a_second_install_at_once_is_refused_not_queued(self):
        self.release()
        os.makedirs(self.state, exist_ok=True)
        fd = os.open(os.path.join(self.state, iw.LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        r = self.install()
        self.assertEqual(r, {"status": "refused", "reason": "another interweave-install is running on this account"})
        self.assertEqual(self.fetched, [])


class Install(Case):
    def test_it_installs_the_pinned_release_with_the_archives_own_install_sh(self):
        art = self.release()
        r = self.install()
        archive_programs = {n: hashlib.sha256(program(n)).hexdigest() for n in PROGRAMS}
        self.assertEqual(r, {"status": "installed", "version": VERSION, "sha256": hashlib.sha256(art).hexdigest(), "programs": archive_programs,
                                  "units": {"running_before": [], "check": "not run: no unit was running"}})
        self.assertEqual(self.installed_names(), sorted(PROGRAMS))
        for n in PROGRAMS:
            self.assertEqual(digest_of(os.path.join(self.bindir, n)), archive_programs[n], n)
            self.assertTrue(os.stat(os.path.join(self.bindir, n)).st_mode & 0o111, n)
        for u in UNITS:
            self.assertTrue(os.path.isfile(os.path.join(self.home, ".config", "systemd", "user", u)), u)
        (url, token, k), = self.fetched
        self.assertEqual((url, token), ("https://api.github.com/repos/o/r/releases/assets/1", TOKEN))
        self.assertEqual(k["max_bytes"], len(art) + 1, "the download is bounded one byte past the pin's size")
        marker = iw.read_marker(self.state)
        self.assertEqual((marker["version"], marker["sha256"], marker["size"], marker["programs"]),
                         (VERSION, hashlib.sha256(art).hexdigest(), len(art), archive_programs))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.state, iw.MARKER)).st_mode), 0o600)
        self.assertEqual([n for n in os.listdir(self.state) if n != iw.LOCK and n != iw.MARKER], [], "no temporary file survives")
        self.assertNotIn(TOKEN, json.dumps(r) + json.dumps(marker), "the token is in neither the reply nor the marker")

    def test_the_second_run_says_current_and_downloads_nothing_until_a_program_changes(self):
        self.release()
        first = self.install()
        again = self.install()
        self.assertEqual(again, {k: v for k, v in {**first, "status": "current"}.items() if k != "units"})
        self.assertEqual(len(self.fetched), 1)
        with open(os.path.join(self.bindir, "transportctl"), "ab") as fh:
            fh.write(b"# edited\n")
        self.assertEqual(self.install()["status"], "installed", "a program that no longer has the recorded digest is replaced")
        self.assertEqual(len(self.fetched), 2)
        os.unlink(os.path.join(self.bindir, "human-desktop"))
        self.assertEqual(self.install()["status"], "installed", "a program that is gone is put back")
        self.assertEqual(self.install()["status"], "current")

    def test_another_pinned_release_is_installed_over_the_marker_of_the_old_one(self):
        self.release()
        self.assertEqual(self.install()["status"], "installed")
        marker = iw.read_marker(self.state)
        marker["version"] = "0.0.9"
        with open(os.path.join(self.state, iw.MARKER), "w") as fh:
            json.dump(marker, fh)
        self.assertEqual(self.install()["status"], "installed")
        self.assertEqual(iw.read_marker(self.state)["version"], VERSION)

    def test_a_digest_that_differs_installs_nothing_and_executes_nothing(self):
        self.release()
        # Another archive of the pinned SIZE is delivered: only the digest tells them apart. Its install.sh would
        # touch the sentinel if anything ran it.
        art = self.artifact
        other = bytearray(art)
        other[len(other) // 2] ^= 0x01
        self.artifact = bytes(other)
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"^sha256 mismatch: the pin says [0-9a-f]{64}, the download is [0-9a-f]{64}; nothing was installed$")
        self.nothing_installed()
        self.artifact = art
        self.assertEqual(self.install()["status"], "installed", "positive control: the pinned archive")

    def test_a_size_that_differs_installs_nothing_though_the_digest_is_right(self):
        self.release()
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin_for(self.artifact, size=len(self.artifact) + 1), fh)
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], rf"^size mismatch: the pin says {len(self.artifact) + 1} bytes, the download is {len(self.artifact)}; nothing was installed$")
        self.nothing_installed()
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin_for(self.artifact), fh)
        self.assertEqual(self.install()["status"], "installed", "positive control: the pin's own size")

    def test_a_member_that_escapes_root_refuses_the_whole_archive(self):
        evil = os.path.join(self._tmp.name, "evil")
        cases = {
            "a parent directory": [("../evil", b"bad", "file")],
            "a parent inside the root": [(f"{ROOT}/../evil", b"bad", "file")],
            "an absolute path": [(evil, b"bad", "file")],
            "another top directory": [("other/x", b"bad", "file")],
            "a name that only starts like the root": [(f"{ROOT}-evil/x", b"bad", "file")],
            "a symlink": [(f"{ROOT}/bin/link", b"/etc", "link")],
            "a symlink to a sibling": [(f"{ROOT}/bin/link", b"transportctl", "link")],
            "a hard link": [(f"{ROOT}/bin/hard", f"{ROOT}/bin/transportctl".encode(), "hardlink")],
            "a device": [(f"{ROOT}/bin/dev", b"", "device")],
            "a member twice": [(f"{ROOT}/README.md", b"again", "file")],
        }
        for label, extra in cases.items():
            self.release(default_members() + extra)
            r = self.install(machine="x86_64")
            self.assertEqual(r["status"], "failed", label)
            self.assertIn("the archive has", r["reason"], label)
            self.nothing_installed(label)
            self.assertFalse(os.path.exists(evil), label)
            self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "root", "evil")), label)
            self.assertFalse(os.path.lexists(os.path.join(self.state, "evil")), label)
        self.release()
        self.assertEqual(self.install()["status"], "installed", "positive control: the same archive without the member")

    def test_the_bounds_on_many_members_and_on_what_unpacks_hold(self):
        self.release()
        self.assertEqual(self.install()["status"], "installed", "positive control")
        for name, value, why in (("MAX_MEMBERS", 3, "more than 3 members"), ("MAX_UNPACKED_BYTES", 10, "more than 10 bytes")):
            shutil.rmtree(self.home)
            os.makedirs(self.home)
            shutil.rmtree(self.state)
            with unittest.mock.patch.object(iw, name, value):
                r = self.install()
            self.assertEqual(r["status"], "failed", name)
            self.assertIn(why, r["reason"], name)
            self.assertEqual(self.installed_names(), [], f"{name}: nothing was installed")

    def test_extraction_writes_only_what_was_judged(self):
        self.release()
        real = iw._judge_members

        def other(tf, root):
            out = real(tf, root)
            info, parts = out[1]
            swapped = tarfile.TarInfo(info.name + "x")
            swapped.size, swapped.type = info.size, info.type
            return [out[0], (swapped, parts)] + out[2:]
        with unittest.mock.patch.object(iw, "_judge_members", other):
            r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("changed between its check and its extraction", r["reason"])
        self.nothing_installed()

    def test_output_that_is_not_utf8_from_install_sh_is_a_failure_with_a_reply(self):
        self.release(members=default_members({"install.sh": (install_sh(after="printf '\\377\\376' >&2", code=1), "exec")}))
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("install.sh exited 1", r["reason"])

    def test_a_directory_a_killed_install_left_is_removed_before_current_and_before_a_missing_token(self):
        self.release()
        self.install()
        left = os.path.join(self.state, iw.WORK, "tree")
        os.makedirs(left)
        self.assertEqual(self.install()["status"], "current")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)), "current does not keep a killed install's 480 MB")
        os.makedirs(left)
        with open(os.path.join(self.bindir, "transportctl"), "ab") as fh:
            fh.write(b"# edited\n")
        self.assertEqual(self.install(token=lambda n: None)["status"], "failed")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)), "nor does a refusal for want of a token")

    def test_an_archive_with_nothing_to_install_from_is_refused(self):
        for label, members in (("no root directory", [(f"{ROOT}/install.sh", install_sh(), "exec")]),
                               ("no install.sh", [m for m in default_members() if not m[0].endswith("install.sh")]),
                               ("install.sh not executable", [(n, c, "file" if n.endswith("install.sh") else k) for n, c, k in default_members()]),
                               ("no bin", [m for m in default_members() if "/bin" not in m[0]])):
            self.release(members)
            r = self.install()
            self.assertEqual(r["status"], "failed", label)
            self.nothing_installed(label)

    def test_an_archive_that_is_not_one_is_a_failure_with_the_digest_right(self):
        self.release(artifact=b"this is not a tarball")
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("could not be extracted", r["reason"])
        self.nothing_installed()

    def test_extraction_gives_modes_by_the_archives_execute_bit_whatever_the_umask(self):
        self.release()
        build = pin_for(self.artifact)["releases"][VERSION]["x86_64"]
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            old = os.umask(0o077)
            try:
                tree = iw.fetch_and_unpack(build, TOKEN, dest, self.fetch)
            finally:
                os.umask(old)
            modes = {n: stat.S_IMODE(os.stat(os.path.join(tree, n)).st_mode)
                     for n in ("install.sh", "bin", "bin/transportctl", "README.md", "systemd/" + UNITS[0])}
        self.assertEqual(modes, {"install.sh": 0o755, "bin": 0o755, "bin/transportctl": 0o755, "README.md": 0o644, "systemd/" + UNITS[0]: 0o644})

    def test_a_version_that_disagrees_with_the_pin_installs_nothing(self):
        cases = {
            "another version": program("transportctl", "transportctl 0.2.0+abcdef123456"),
            "a suffix more": program("transportctl", REPORTS["transportctl"] + " extra"),
            "nothing printed": program("transportctl", ""),
            "an exit 3": program("transportctl", code=3),
        }
        for label, content in cases.items():
            self.release(default_members({"bin/transportctl": (content, "exec"), "install.sh": (install_sh(f"touch {self.sentinel}"), "exec")}))
            r = self.install()
            self.assertEqual(r["status"], "failed", label)
            self.assertIn("nothing was installed", r["reason"], label)
            self.assertIn("transportctl", r["reason"], label)
            self.nothing_installed(label)
        self.release(default_members({"install.sh": (install_sh(f"touch {self.sentinel}"), "exec")}))
        self.assertEqual(self.install()["status"], "installed", "positive control")
        self.assertTrue(os.path.exists(self.sentinel), "…and install.sh does run when the versions agree")

    def test_a_program_the_pin_expects_but_the_archive_lacks_installs_nothing(self):
        self.release([m for m in default_members() if not m[0].endswith("bin/transport-daemon")])
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("transport-daemon", r["reason"])
        self.nothing_installed()

    def test_a_version_that_disagrees_once_installed_is_a_failure_and_no_marker(self):
        # Same bytes, so the digests agree; the program says another thing from ~/.local/bin than from the archive.
        script = (b"#!/bin/sh\ncase \"$0\" in */.local/bin/*) echo 'transportctl 9.9.9';; *) echo '" + REPORTS["transportctl"].encode() + b"';; esac\n")
        self.release(default_members({"bin/transportctl": (script, "exec")}))
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("the installed programs disagree with the pin", r["reason"])
        self.assertIsNone(iw.read_marker(self.state))
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)))
        self.assertNotEqual(self.install()["status"], "current", "no marker, so the next run installs again")

    def test_an_install_sh_that_fails_or_installs_something_else_is_a_failure(self):
        cases = {
            "an exit 1 with a word": (install_sh("echo 'install.sh: no executable x' >&2; exit 1"), "install.sh exited 1: install.sh: no executable x"),
            "a missing program after a clean exit": (install_sh().replace(b"human-desktop interweave-human; do", b"interweave-human; do"), "human-desktop is not in"),
            "a program that is not the archive's": (install_sh(after="echo '#!/bin/sh' > \"$HOME/.local/bin/transportctl\""), "transportctl in"),
            "no unit templates": (install_sh().replace(b'cp "$here/systemd/$unit"', b'true "$here/systemd/$unit"'), "interweave-daemon@.service is not in"),
        }
        for label, (content, why) in cases.items():
            self.release(default_members({"install.sh": (content, "exec")}))
            r = self.install()
            self.assertEqual(r["status"], "failed", label)
            self.assertIn(why, r["reason"], label)
            self.assertIsNone(iw.read_marker(self.state), label)
            self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)), label)
            shutil.rmtree(self.home)
            os.makedirs(self.home)

    def test_an_install_sh_that_never_ends_is_a_failure_within_the_bound(self):
        self.release(default_members({"install.sh": (install_sh("sleep 30"), "exec")}))
        with unittest.mock.patch.object(iw, "INSTALL_SH_TIMEOUT_S", 0.5):
            r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("install.sh did not finish within", r["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)))

    def test_install_sh_runs_with_a_minimal_environment_never_the_sessions(self):
        seen = os.path.join(self._tmp.name, "env")
        self.release(default_members({"install.sh": (install_sh(f"env > {seen}"), "exec")}))
        with unittest.mock.patch.dict(os.environ, {"GH_TOKEN": TOKEN, "SOME_SECRET": "s3", "XDG_RUNTIME_DIR": "/run/user/1", "AGENT_FABRIC_X": "y"}):
            self.assertEqual(self.install()["status"], "installed")
        env = dict(line.split("=", 1) for line in rd(seen).splitlines() if "=" in line)
        self.assertNotIn(TOKEN, rd(seen))
        self.assertEqual(env["HOME"], self.home)
        self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/1", "the user manager is reachable")
        self.assertEqual(sorted(k for k in env if k not in ("PWD", "SHLVL", "_", "OLDPWD")), ["HOME", "LC_ALL", "PATH", "XDG_RUNTIME_DIR"])

    def test_the_units_go_where_xdg_config_home_says(self):
        cfg = os.path.join(self._tmp.name, "cfg")
        self.release()
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": cfg}):
            self.assertEqual(self.install()["status"], "installed")
            self.assertEqual(iw.installed(self.home, self.state, root=self.root)["units"], {u: True for u in UNITS})
        self.assertTrue(os.path.isfile(os.path.join(cfg, "systemd", "user", UNITS[0])))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config")))

    def test_the_temporary_directory_goes_however_the_install_ends(self):
        self.release()
        os.makedirs(os.path.join(self.state, iw.WORK, "tree", "old"))
        with open(os.path.join(self.state, iw.WORK, "tree", "old", "leftover"), "w") as fh:
            fh.write("a killed install's")
        seen = {}

        def fetch(url, token, dest, **k):
            seen["leftover"] = os.path.exists(os.path.join(self.state, iw.WORK, "tree", "old"))
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.install(fetch=fetch)
        self.assertEqual(seen, {"leftover": False}, "a killed install's directory was removed at the start")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)), "…and this one's, interrupted, at the end")
        self.nothing_installed()

    def test_a_failed_download_says_what_failed_without_the_token(self):
        import urllib.error
        self.release()
        for exc, want in ((urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b"")), "HTTP 404"),
                          (urllib.error.URLError(f"boom {TOKEN}"), "<token>"),
                          (TimeoutError(f"slow {TOKEN}"), "<token>"),
                          (ValueError("the download is larger than 5 bytes"), "larger than 5 bytes")):
            def fetch(url, token, dest, _e=exc, **k):
                raise _e
            r = self.install(fetch=fetch)
            self.assertEqual(r["status"], "failed", repr(exc))
            self.assertIn(want, r["reason"], repr(exc))
            self.assertNotIn(TOKEN, r["reason"], repr(exc))
            self.nothing_installed()

    def test_an_endless_download_stops_at_the_pinned_size(self):
        size = 4096
        pin = pin_for(b"x" * size)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(size * 3))
                self.end_headers()
                try:
                    self.wfile.write(b"x" * size * 3)
                except OSError:
                    pass

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        build = {**pin["releases"][VERSION]["x86_64"], "url": f"http://127.0.0.1:{srv.server_address[1]}/a"}
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            with self.assertRaisesRegex(iw.InstallError, r"the download failed \(the download is larger than 4097 bytes\)"):
                iw.fetch_and_unpack(build, TOKEN, dest)
            self.assertEqual(os.listdir(dest), [], "the part file is removed")


class FetchAndUnpack(Case):
    def test_it_runs_nothing_touches_no_home_and_returns_the_root(self):
        self.release(default_members({"install.sh": (install_sh(f"touch {self.sentinel}"), "exec")}))
        build = pin_for(self.artifact)["releases"][VERSION]["x86_64"]
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            tree = iw.fetch_and_unpack(build, TOKEN, dest, self.fetch)
            self.assertEqual(tree, os.path.join(dest, ROOT))
            self.assertEqual(sorted(os.listdir(os.path.join(tree, "bin"))), sorted(PROGRAMS))
            self.assertTrue(os.access(os.path.join(tree, "install.sh"), os.X_OK))
            self.assertFalse(os.access(os.path.join(tree, "README.md"), os.X_OK))
            self.assertEqual(os.listdir(dest), [ROOT], "the download is not left beside the tree")
        self.assertFalse(os.path.exists(self.sentinel))
        self.assertEqual(os.listdir(self.home), [], "HOME is untouched")

    def test_the_directory_must_exist_and_be_empty(self):
        self.release()
        build = pin_for(self.artifact)["releases"][VERSION]["x86_64"]
        with self.assertRaisesRegex(iw.InstallError, "does not exist"):
            iw.fetch_and_unpack(build, TOKEN, os.path.join(self._tmp.name, "nope"), self.fetch)
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            open(os.path.join(dest, "x"), "w").close()
            with self.assertRaisesRegex(iw.InstallError, "not empty"):
                iw.fetch_and_unpack(build, TOKEN, dest, self.fetch)
        self.assertEqual(self.fetched, [])


class Read(Case):
    def read(self):
        return iw.installed(self.home, self.state, root=self.root, run=self.systemd)

    def test_nothing_installed_is_absent_with_the_units_said(self):
        self.release()
        self.assertEqual(self.read(), {"status": "absent", "units": {u: False for u in UNITS}})

    def test_an_install_reads_back_its_version_digests_and_units(self):
        art = self.release()
        r = self.install()
        got = self.read()
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["version"], VERSION)
        self.assertEqual(got["reports"], REPORTS, "only the programs the pin says report a version are run")
        self.assertEqual(sorted(got["programs"]), sorted(PROGRAMS), "all of them are digested")
        self.assertEqual(got["programs"], r["programs"])
        self.assertEqual(got["release_sha256"], hashlib.sha256(art).hexdigest())
        self.assertIs(got["pinned"], True)
        self.assertEqual(got["units"], {u: True for u in UNITS})

    def test_a_program_that_changed_loses_the_release_digest_and_one_that_reports_another_version_is_not_pinned(self):
        self.release()
        self.install()
        path = os.path.join(self.bindir, "human-desktop")
        with open(path, "ab") as fh:
            fh.write(b"# edited\n")
        got = self.read()
        self.assertEqual(got["status"], "ok")
        self.assertNotIn("release_sha256", got, "the marker no longer vouches for what is there")
        with open(os.path.join(self.bindir, "transportctl"), "wb") as fh:
            fh.write(program("transportctl", "transportctl 0.2.0+abc"))
        got = self.read()
        self.assertEqual(got["status"], "unreadable", "two versions at once are not one version")
        self.assertIn("one version", got["reason"])
        self.assertNotIn("version", got)

    def test_a_program_that_will_not_report_is_unreadable_never_a_guessed_version(self):
        self.release()
        self.install()
        for label, content, why in (("an exit 3", program("transportctl", code=3), "exited 3"),
                                    ("no version in it", program("transportctl", "hello"), "one version"),
                                    ("not an executable", None, "not an executable file")):
            path = os.path.join(self.bindir, "transportctl")
            os.unlink(path)
            with open(path, "wb") as fh:
                fh.write(content or b"x")
            os.chmod(path, 0o755 if content else 0o644)
            got = self.read()
            self.assertEqual(got["status"], "unreadable", label)
            self.assertIn(why, got["reason"], label)
            self.assertNotIn("version", got, label)

    def test_a_pin_that_cannot_be_read_still_reads_what_the_marker_names(self):
        self.release()
        self.install()
        os.unlink(os.path.join(self.root, iw.PIN_REL))
        got = self.read()
        self.assertEqual(got["status"], "ok")
        self.assertNotIn("pinned", got, "unknown stays unknown")
        shutil.rmtree(self.state)
        self.assertEqual(self.read()["status"], "unreadable")


class Channel(Case):
    """ADR-064 rule 14: the units that were running are restarted and checked; a check that fails puts the previous programs back."""

    def seed_old(self, names=("transportctl", "transport-daemon")) -> dict:
        os.makedirs(self.bindir)
        old = {}
        for n in names:
            body = program(n, f"{n} 0.0.9+old")
            with open(os.path.join(self.bindir, n), "wb") as fh:
                fh.write(body)
            os.chmod(os.path.join(self.bindir, n), 0o755)
            old[n] = hashlib.sha256(body).hexdigest()
        return old

    def bin_digests(self) -> dict:
        return {n: digest_of(os.path.join(self.bindir, n)) for n in self.installed_names() if not n.startswith(".")}

    def assert_previous_back(self, old):
        self.assertEqual(self.bin_digests(), old, "the programs the account had are back and nothing else is left")
        self.assertIsNone(iw.read_marker(self.state), "no marker for programs that did not stay")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)))
        self.assertEqual([n for n in self.installed_names() if n.startswith(".")], [], "no temporary file in the bin directory")

    def test_nothing_running_means_no_restart_and_the_reply_says_so(self):
        self.release()
        r = self.install()
        self.assertEqual((r["status"], r["units"]), ("installed", {"running_before": [], "check": "not run: no unit was running"}))
        self.assertEqual(self.systemd.restarts, [])
        self.assertEqual(self.systemd.status_calls, 0)

    def test_no_user_manager_is_nothing_running_as_install_sh_takes_it(self):
        self.release()
        self.systemd.manager = False
        r = self.install()
        self.assertEqual((r["status"], r["units"]["running_before"]), ("installed", []))

    def test_exactly_the_units_that_were_running_are_restarted_daemon_first_and_checked(self):
        self.release()
        self.systemd.states = {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}
        r = self.install()
        self.assertEqual((r["status"], r["units"]), ("installed", {"running_before": [DAEMON_UNIT, CLIENT_UNIT], "check": "passed"}))
        self.assertEqual(self.systemd.restarts, [DAEMON_UNIT, CLIENT_UNIT])
        self.assertGreaterEqual(self.systemd.status_calls, 1, "the carrier is asked when its client runs")
        self.assertIsNotNone(iw.read_marker(self.state))

    def test_a_unit_that_was_not_running_is_not_started(self):
        self.release()
        self.systemd.states = {DAEMON_UNIT: "active", CLIENT_UNIT: "inactive"}
        r = self.install()
        self.assertEqual((r["status"], self.systemd.restarts, self.systemd.status_calls), ("installed", [DAEMON_UNIT], 0))
        self.assertEqual(self.systemd.states[CLIENT_UNIT], "inactive")

    def test_a_unit_that_does_not_come_back_restores_the_previous_programs_and_says_failed_with_both_checks(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        calls = []

        def on_restart(unit):
            calls.append(unit)
            self.systemd.after_restart[DAEMON_UNIT] = "failed" if len(calls) == 1 else "active"     # the old programs come back up
        self.systemd.on_restart = on_restart
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIs(r["restored"], True)
        self.assertEqual(self.systemd.restarts, [DAEMON_UNIT, DAEMON_UNIT], "restarted again on the restored programs")
        first, second = r["checks"]
        self.assertEqual((first["status"], second["status"]), ("failed", "passed"))
        self.assertIn("failed", r["reason"])
        self.assertIn("check: passed", r["reason"])
        self.assert_previous_back(old)

    def test_a_restore_that_cannot_bring_the_channel_back_says_so_in_the_second_result(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.after_restart[DAEMON_UNIT] = "failed"
        r = self.install()
        self.assertEqual((r["status"], r["checks"][0]["status"], r["checks"][1]["status"]), ("failed", "failed", "failed"))
        self.assert_previous_back(old)

    def test_a_program_that_did_not_exist_before_is_removed_by_the_restore(self):
        self.release()
        old = self.seed_old(("transportctl",))
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.after_restart[DAEMON_UNIT] = "failed"
        self.install()
        self.assert_previous_back(old)
        self.assertNotIn("human-desktop", self.installed_names())

    def test_the_carrier_not_answering_after_the_restart_restores(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}
        self.systemd.status_rcs = [3]
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("status exited 3", r["checks"][0]["reason"])
        self.assertEqual(self.systemd.restarts, [DAEMON_UNIT, CLIENT_UNIT, DAEMON_UNIT, CLIENT_UNIT])
        self.assert_previous_back(old)

    def test_a_carrier_that_answers_on_a_later_look_passes(self):
        self.release()
        self.systemd.states = {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}
        self.systemd.status_rcs = [3, 3, 0]
        self.assertEqual(self.install()["status"], "installed")
        self.assertEqual(self.systemd.status_calls, 3)

    def test_a_crash_loop_is_not_a_start(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        seq = iter(["active", "activating", "active", "activating", "active", "activating", "active", "activating", "active", "activating"])
        real = self.systemd.__call__

        def flap(argv, **kw):
            if os.path.basename(argv[0]) == "systemctl" and argv[2] == "show" and self.systemd.restarts:
                return subprocess.CompletedProcess(argv, 0, next(seq) + "\n", "")
            return real(argv, **kw)
        r = self.install(run=flap)
        self.assertEqual(r["status"], "failed", "active on one look and not on the next is not two active looks in a row")
        self.assertEqual(self.bin_digests(), old)

    def test_a_daemon_that_prints_another_version_once_restarted_restores(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        real = self.systemd.__call__

        def drifting(argv, **kw):
            if os.path.basename(argv[0]) == "transport-daemon" and self.systemd.restarts:
                return subprocess.CompletedProcess(argv, 0, "transport-daemon 9.9.9\n", "")
            return real(argv, **kw)
        r = self.install(run=drifting)
        self.assertEqual(r["status"], "failed")
        self.assertIn("transport-daemon --version prints", r["checks"][0]["reason"])
        self.assert_previous_back(old)

    def test_a_restart_the_manager_refuses_restores(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.restart_rc[DAEMON_UNIT] = 1
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("exited 1", r["checks"][0]["reason"])
        self.assert_previous_back(old)

    def test_a_restart_that_hangs_is_a_failure_within_the_bound_and_restores(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.hang = "restart"
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("did not finish", r["checks"][0]["reason"])
        self.assert_previous_back(old)

    def test_a_manager_that_does_not_answer_before_the_install_installs_nothing(self):
        self.release()
        self.systemd.hang = "show"
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("not known", r["reason"])
        self.nothing_installed("unknown is not 'not running'")

    def test_a_version_that_disagrees_after_install_sh_restores_without_a_restart(self):
        self.release(members=default_members({"install.sh": (install_sh(after='printf "%s" \'#!/bin/sh\necho transport-daemon 9.9.9\' > "$HOME/.local/bin/transport-daemon"'), "exec")}))
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        r = self.install()
        self.assertEqual((r["status"], r["restored"]), ("failed", True))
        self.assertEqual(self.systemd.restarts, [], "the units were never restarted onto programs that were already wrong")
        self.assert_previous_back(old)

    def test_an_install_sh_that_fails_midway_puts_the_previous_programs_back(self):
        self.release(members=default_members({"install.sh": (install_sh(code=1), "exec")}))
        old = self.seed_old()
        r = self.install()
        self.assertEqual((r["status"], r["restored"]), ("failed", True))
        self.assert_previous_back(old)

    def test_a_roster_that_cannot_be_read_installs_nothing(self):
        self.release()
        os.unlink(os.path.join(self.root, iw.ROSTER_REL))
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("roster", r["reason"])
        self.nothing_installed()

    def test_the_read_says_whether_the_channel_is_up(self):
        self.release()
        self.install()
        self.assertEqual(self.read_channel()["status"], "not-running")
        self.systemd.states = {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}
        c = self.read_channel()
        self.assertEqual((c["status"], c["units"]), ("ok", {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}))
        self.systemd.status_rcs = [3]
        c = self.read_channel()
        self.assertEqual(c["status"], "off")
        self.assertIn("status exited 3", c["reason"])
        self.systemd.status_rcs = [0]
        self.systemd.states[DAEMON_UNIT] = "failed"
        self.systemd.states[CLIENT_UNIT] = "active"
        self.assertEqual(self.read_channel()["status"], "ok", "a unit that is not running is not the check's business")
        self.systemd.states[CLIENT_UNIT] = "activating"
        self.assertEqual(self.read_channel()["status"], "off", "a unit that runs but is not active is off the channel")
        self.systemd.hang = "show"
        self.assertEqual(self.read_channel()["status"], "unknown")

    def read_channel(self):
        return iw.installed(self.home, self.state, root=self.root, run=self.systemd)["channel"]


class Wiring(Case):
    def test_the_op_is_an_operator_action_and_the_read_an_operator_read(self):
        self.assertIn("interweave-install", ops.OPS)
        self.assertIn("interweave-install", ACTION_OPS)
        self.assertIn("interweave", ops.OPS)
        self.assertNotIn("interweave", ACTION_OPS)
        for op in ("interweave", "interweave-install"):
            self.assertNotIn(op, ops.PUBLIC_OPS)
        self.assertIn("interweave", agentd.BESIDE_LOOP_OPS, "the read hashes ~480 MB and runs programs: it does not hold the loop")

    def test_the_daemon_answers_both_in_the_wires_reply_shape(self):
        self.release()
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-25T10:00:00.000Z", "home": self.home, "root": self.root,
               "carrier_install_opts": {"state": self.state, "fetch": self.fetch, "token": lambda n: TOKEN, "machine": "x86_64"},
               "carrier_opts": {"state": self.state}}
        r = agentd.answer({"id": "q", "op": "interweave-install", "to": "*", "from": "h/user"}, ctx)
        self.assertEqual((r["op"], list(r["data"]), r["data"]["interweave-install"]["status"]), ("interweave-install", ["interweave-install", "agentd"], "installed"))
        r = agentd.answer({"id": "q2", "op": "interweave", "to": "*", "from": "h/user"}, ctx)
        self.assertEqual((list(r["data"]), r["data"]["interweave"]["status"], r["data"]["interweave"]["version"]), (["interweave", "agentd"], "ok", VERSION))
        r = agentd.answer({"id": "q3", "op": "interweave-install", "to": "*", "args": {"url": "https://x"}, "from": "h/user"}, ctx)
        self.assertEqual(r["data"]["interweave-install"]["status"], "refused")


class Operator(unittest.TestCase):
    def test_the_verbs_take_no_arguments(self):
        a = ctl.parse_args(["all", "interweave-install"])
        self.assertEqual((a["op"], a["targets"], a["timeout"]), ("interweave-install", ["all"], iw.CARRIER_INSTALL_BUDGET_S))
        for argv, said in ((["all", "interweave-install", "--version", "0.1.0"], "with upgrade and gateway-install only"),
                           (["all", "interweave", "--version", "0.1.0"], "with upgrade and gateway-install only")):
            with self.assertRaises(ctl.CtlError, msg=argv) as cm:
                ctl.parse_args(argv)
            self.assertIn(said, str(cm.exception))
        self.assertEqual(ctl.parse_args(["a", "interweave"])["op"], "interweave")
        self.assertIn("interweave-install   (an action", ctl.USAGE)

    def test_the_request_carries_no_arguments_and_is_an_action(self):
        args = ctl.parse_args(["all", "interweave-install"])
        req = ctl.build_request(args, id="i", from_="h/user", to="*", cfg={"ttl_s": 30})
        self.assertNotIn("args", req, "no url, digest, size or path is in a request")
        self.assertIn(req["op"], ACTION_OPS)

    def test_the_tables_say_each_account_and_never_an_unanswered_one_as_installed(self):
        rows = [{"account": "a", "status": "ok", "interweaveInstall": {"status": "installed", "version": VERSION, "sha256": "ab" * 32},
                 "interweave": {"status": "ok", "version": VERSION, "pinned": True, "units": {u: True for u in UNITS}}},
                {"account": "b", "status": "no answer"},
                {"account": "c", "status": "ok", "interweaveInstall": {"status": "failed", "version": VERSION,
                                                                          "reason": "sha256 mismatch: x\u0007"},
                 "interweave": {"status": "absent", "units": {u: False for u in UNITS}}}]
        install = ctl.table("interweave-install", rows).split("\n")
        self.assertRegex(install[1], r"^a +installed +0\.1\.0 +abababababab")
        self.assertEqual(install[2].split()[:2], ["b", "no"])
        self.assertIn("sha256 mismatch", install[3])
        self.assertNotIn("\u0007", install[3], "an account's words reach the terminal escaped")
        read = ctl.table("interweave", rows).split("\n")
        self.assertRegex(read[1], r"^a +ok +0\.1\.0 +yes +both")
        self.assertRegex(read[3], r"^c +absent +- +- +no")
        self.assertIn("installed", ctl.ACTION_OK["interweave-install"])
        self.assertIn("current", ctl.ACTION_OK["interweave-install"])
        self.assertNotIn("failed", ctl.ACTION_OK["interweave-install"])
        self.assertNotIn("refused", ctl.ACTION_OK["interweave-install"])


if __name__ == "__main__":
    unittest.main()
