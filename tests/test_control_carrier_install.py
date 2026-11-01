#!/usr/bin/env python3
"""Tests for tools/fabric/control/carrier_install.py: the `interweave-install` action and the `interweave` read
(agent-fabric ADR-064 §5 rule 4). The release is an archive built here with the layout of the real one
(<root>/bin, <root>/systemd, <root>/install.sh) whose install.sh does what the real one does to HOME; the
download is a fake that writes it (a real local HTTP server where the size bound is the subject). Nothing reaches
the network and nothing is installed outside the scratch directories."""
from __future__ import annotations

import base64
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


# A signing key of the tests' own (an Ed25519 seed fixed here so a run is repeatable; public test data, never a credential), filed under a minisign key id.
# Signing is the secret half of RFC 8032 section 5.1.6; the verifier under test shares its curve constants and nothing else.
FIXTURE_ENTROPY = hashlib.sha256(b"test_control_carrier_install signer one").digest()
KEY_ID = bytes.fromhex("0102030405060708")
OTHER_FIXTURE_ENTROPY = hashlib.sha256(b"test_control_carrier_install signer two").digest()
COMMENT = "timestamp:1793172713\tfile:{name}\thashed"


def _encode(p) -> bytes:
    zi = pow(p[2], -1, iw.minisign._P)
    x, y = p[0] * zi % iw.minisign._P, p[1] * zi % iw.minisign._P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def ed_public(entropy: bytes) -> bytes:
    a = int.from_bytes(hashlib.sha512(entropy).digest()[:32], "little")
    a = (a & ~7 & ((1 << 254) - 1)) | (1 << 254)
    return _encode(iw.minisign._mul(a, iw.minisign._B))


def ed_sign(entropy: bytes, message: bytes) -> bytes:
    h = hashlib.sha512(entropy).digest()
    a = (int.from_bytes(h[:32], "little") & ~7 & ((1 << 254) - 1)) | (1 << 254)
    pub = ed_public(entropy)
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % iw.minisign._L
    big_r = _encode(iw.minisign._mul(r, iw.minisign._B))
    k = int.from_bytes(hashlib.sha512(big_r + pub + message).digest(), "little") % iw.minisign._L
    return big_r + ((r + k * a) % iw.minisign._L).to_bytes(32, "little")


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def public_key_line(entropy: bytes = FIXTURE_ENTROPY, key_id: bytes = KEY_ID) -> str:
    return b64(b"Ed" + key_id + ed_public(entropy))


def minisig_for(artifact: bytes, name: str, entropy: bytes = FIXTURE_ENTROPY, key_id: bytes = KEY_ID, comment: str | None = None, kind: bytes = b"ED") -> dict:
    """The three lines of the .minisig minisign would write: the prehashed kind signs the BLAKE2b-512 of the file, the legacy kind the file."""
    message = hashlib.blake2b(artifact, digest_size=64).digest() if kind == b"ED" else artifact
    sig = kind + key_id + ed_sign(entropy, message)
    comment = COMMENT.format(name=name) if comment is None else comment
    return {"signature": b64(sig), "trusted_comment": comment, "global_signature": b64(ed_sign(entropy, sig[10:] + comment.encode()))}


def pin_for(artifact: bytes, signed: bool = True, **over) -> dict:
    """A pin for the artifact, signed by the tests' key unless `signed` is false (then the release is `unsigned`)."""
    name = over.get("name", f"{ROOT}.tar.gz")
    b = {"url": "https://api.github.com/repos/o/r/releases/assets/1", "name": name, "size": len(artifact),
         "sha256": hashlib.sha256(artifact).hexdigest(), "root": ROOT, "reports": REPORTS, **over}
    rel = {"tag": f"v{VERSION}", "commit": "a" * 40, "release_run": "run 1", "x86_64": b}
    if signed:
        rel["minisign"] = {"public_key": public_key_line(), "key_id": iw.minisign.key_id_text(KEY_ID), "release_keys_commit": "b" * 40}
        b.setdefault("minisig", minisig_for(artifact, name))
    else:
        rel["unsigned"] = "the fixture predates the key"
    return {"version": 1, "description": "fixture", "current": VERSION, "releases": {VERSION: rel}}


def released(artifact: bytes, **over) -> tuple[dict, dict]:
    release = pin_for(artifact, **over)["releases"][VERSION]
    return release, release["x86_64"]


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
        self.proc: str | None = None                   # a directory standing for /proc; set by the case
        self.bindir: str | None = None
        self.exe: str | None = None                    # what the daemon's /proc/<pid>/exe says (default: the installed file)
        self.main_pid = 4242
        self.props = "SubState=auto-restart\nResult=exit-code\nExecMainStatus=1\nNRestarts=7\n"   # the diagnosis's `show`
        self.journal = "transport-daemon: cannot bind 127.0.0.1:47130: address in use\n"
        self.journal_rc = 0

    def __call__(self, argv, **kw):
        name = os.path.basename(argv[0])
        if name not in ("systemctl", "gzcoord-carrier", "journalctl"):
            return subprocess.run(argv, **kw)
        self.calls.append(list(argv))
        done = lambda rc=0, out="": subprocess.CompletedProcess(argv, rc, out, "")   # noqa: E731
        if name == "journalctl":
            if self.hang == "journal":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return done(self.journal_rc, self.journal)
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
            if argv[3].startswith("--property=SubState"):
                return done(0, self.props)
            if argv[3] == "--property=MainPID":
                d = os.path.join(self.proc, str(self.main_pid))
                os.makedirs(d, exist_ok=True)
                link = os.path.join(d, "exe")
                if os.path.lexists(link):
                    os.unlink(link)
                os.symlink(self.exe or os.path.realpath(os.path.join(self.bindir, "transport-daemon")), link)
                return done(0, f"{self.main_pid}\n")
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


CLIENT_BYTES = b"#!/bin/sh\n# the clone's client unit program\n"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="test_control_carrier_install.")
        self.addCleanup(self._tmp.cleanup)
        t = self._tmp.name
        self.root, self.home, self.state = (os.path.join(t, n) for n in ("root", "home", "state"))
        for d in (os.path.join(self.root, "runtime", "interweave"), self.home):
            os.makedirs(d)
        with open(os.path.join(self.root, "runtime", "interweave", "client"), "wb") as fh:
            fh.write(CLIENT_BYTES)
        with open(os.path.join(self.root, iw.ROSTER_REL), "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199], "rows": []}, fh)
        self.systemd = Systemd()
        self.events: list[str] = []
        self.lease_refused: iw.LeaseRefused | None = None
        self.systemd.proc = os.path.join(t, "proc")
        self.systemd.bindir = os.path.join(self.home, ".local", "bin")
        os.makedirs(self.systemd.proc)
        patcher_proc = unittest.mock.patch.object(iw, "PROC_ROOT", self.systemd.proc)
        patcher_proc.start()
        self.addCleanup(patcher_proc.stop)
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

    def lease(self, root, wait_s, name):
        self.events.append(f"lease {name} wait_s={wait_s}")
        if self.lease_refused:
            raise self.lease_refused
        case = self

        class Turn:
            def release(self):
                case.events.append("release")
        return Turn()

    def fetch(self, url, token, dest, **k):
        self.events.append("fetch")
        self.fetched.append((url, token, k))
        with open(dest, "wb") as fh:
            fh.write(self.artifact)
        return len(self.artifact), hashlib.sha256(self.artifact).hexdigest()

    def logged_run(self, argv, **kw):
        self.events.append(f"run {os.path.basename(argv[0])}")
        return self.systemd(argv, **kw)

    def install(self, request=None, **kw):
        opts = dict(root=self.root, home=self.home, state=self.state, fetch=self.fetch, token=lambda name: TOKEN, machine="x86_64",
                    run=self.logged_run, sleep=lambda s: None, lease=self.lease)
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
        self.assertEqual(r, {"status": "refused", "reason": iw.LOCK_BUSY})
        self.assertEqual(self.fetched, [])


class Install(Case):
    def test_it_installs_the_pinned_release_with_the_archives_own_install_sh(self):
        art = self.release()
        r = self.install()
        archive_programs = {n: hashlib.sha256(program(n)).hexdigest() for n in PROGRAMS}
        self.assertEqual(r, {"status": "installed", "version": VERSION, "sha256": hashlib.sha256(art).hexdigest(), "programs": archive_programs,
                                  "client": "installed", "units": {"running_before": [], "check": "not run: no unit was running"}})
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
        self.assertEqual(again, {k: v for k, v in {**first, "status": "current", "client": "already"}.items() if k != "units"})
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
        release, build = released(self.artifact)
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            old = os.umask(0o077)
            try:
                tree = iw.fetch_and_unpack(release, build, TOKEN, dest, self.fetch)
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
        release = pin["releases"][VERSION]
        build = {**release["x86_64"], "url": f"http://127.0.0.1:{srv.server_address[1]}/a"}
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            with self.assertRaisesRegex(iw.InstallError, r"the download failed \(the download is larger than 4097 bytes\)"):
                iw.fetch_and_unpack(release, build, TOKEN, dest)
            self.assertEqual(os.listdir(dest), [], "the part file is removed")


class FetchAndUnpack(Case):
    def test_it_runs_nothing_touches_no_home_and_returns_the_root(self):
        self.release(default_members({"install.sh": (install_sh(f"touch {self.sentinel}"), "exec")}))
        release, build = released(self.artifact)
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            tree = iw.fetch_and_unpack(release, build, TOKEN, dest, self.fetch)
            self.assertEqual(tree, os.path.join(dest, ROOT))
            self.assertEqual(sorted(os.listdir(os.path.join(tree, "bin"))), sorted(PROGRAMS))
            self.assertTrue(os.access(os.path.join(tree, "install.sh"), os.X_OK))
            self.assertFalse(os.access(os.path.join(tree, "README.md"), os.X_OK))
            self.assertEqual(os.listdir(dest), [ROOT], "the download is not left beside the tree")
        self.assertFalse(os.path.exists(self.sentinel))
        self.assertEqual(os.listdir(self.home), [], "HOME is untouched")

    def test_the_directory_must_exist_and_be_empty(self):
        self.release()
        release, build = released(self.artifact)
        with self.assertRaisesRegex(iw.InstallError, "does not exist"):
            iw.fetch_and_unpack(release, build, TOKEN, os.path.join(self._tmp.name, "nope"), self.fetch)
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            open(os.path.join(dest, "x"), "w").close()
            with self.assertRaisesRegex(iw.InstallError, "not empty"):
                iw.fetch_and_unpack(release, build, TOKEN, dest, self.fetch)
        self.assertEqual(self.fetched, [])


class Ed25519(unittest.TestCase):
    # RFC 8032 section 7.1: (secret entropy, public key, message, signature).
    VECTORS = (
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
        ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7", "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
         "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    )

    def test_the_rfc_8032_test_vectors_verify_and_a_changed_bit_does_not(self):
        for entropy, public, message, signature in self.VECTORS:
            pub, msg, sig = (bytes.fromhex(x) for x in (public, message, signature))
            self.assertEqual(ed_public(bytes.fromhex(entropy)), pub, "the tests' signer derives the RFC's public key")
            self.assertEqual(ed_sign(bytes.fromhex(entropy), msg), sig, "and its signature")
            self.assertTrue(iw.minisign.ed25519_verify(pub, msg, sig), f"vector {public[:8]}")
            self.assertFalse(iw.minisign.ed25519_verify(pub, msg + b"\0", sig), "control: another message")
            self.assertFalse(iw.minisign.ed25519_verify(pub, msg, sig[:-1] + bytes([sig[-1] ^ 1])), "control: S changed")
            self.assertFalse(iw.minisign.ed25519_verify(pub, msg, bytes([sig[0] ^ 1]) + sig[1:]), "control: R changed")

    def test_a_signature_whose_s_is_not_reduced_is_refused(self):
        entropy, public, message, signature = self.VECTORS[0]
        sig = bytes.fromhex(signature)
        s_plus_l = (int.from_bytes(sig[32:], "little") + iw.minisign._L).to_bytes(32, "little")
        self.assertFalse(iw.minisign.ed25519_verify(bytes.fromhex(public), b"", sig[:32] + s_plus_l))

    def test_a_key_or_signature_of_the_wrong_length_or_off_the_curve_is_false_not_an_exception(self):
        entropy, public, message, signature = self.VECTORS[0]
        self.assertFalse(iw.minisign.ed25519_verify(b"\0" * 31, b"", bytes.fromhex(signature)))
        self.assertFalse(iw.minisign.ed25519_verify(bytes.fromhex(public), b"", b"\0" * 63))
        self.assertFalse(iw.minisign.ed25519_verify(b"\xff" * 32, b"", bytes.fromhex(signature)), "y >= p")


class RealPin(unittest.TestCase):
    """The committed pin read by the real reader: the data and the code that judges it together."""

    def test_v0_2_0_is_signed_and_its_signature_shape_passes_the_real_pin_problem(self):
        pin = iw.load_pin(HERE)
        self.assertEqual(pin["current"], "0.2.0")
        rel = pin["releases"]["0.2.0"]
        self.assertNotIn("unsigned", rel)
        self.assertEqual(rel["minisign"]["key_id"], "5B8EC2921F6805E1")
        self.assertIn("unsigned", pin["releases"]["0.1.0"], "v0.1.0 predates the key")
        self.assertNotIn("minisign", pin["releases"]["0.1.0"])

    def test_the_trusted_comments_signature_verifies_with_the_pinned_key_and_names_the_archive(self):
        # The archive is 117 MB and is not here; the global signature covers the comment and the archive's signature, so
        # it ties the pinned bytes to the pinned key without it. verify_file itself runs on the archive in the live check.
        rel = iw.load_pin(HERE)["releases"]["0.2.0"]
        build = rel["x86_64"]
        key = base64.b64decode(rel["minisign"]["public_key"])
        sig = base64.b64decode(build["minisig"]["signature"])
        comment = build["minisig"]["trusted_comment"]
        glob = base64.b64decode(build["minisig"]["global_signature"])
        self.assertTrue(iw.minisign.ed25519_verify(key[10:], sig[10:] + comment.encode(), glob))
        self.assertFalse(iw.minisign.ed25519_verify(key[10:], sig[10:] + comment.encode() + b"x", glob), "control: an edited comment")
        self.assertIn(f"file:{build['name']}", comment.split("\t"))

    def test_a_pin_with_the_real_fields_broken_one_at_a_time_is_refused(self):
        with open(os.path.join(HERE, iw.PIN_REL)) as fh:
            good = json.load(fh)
        self.assertIsNone(iw.pin_problem(good), "positive control")
        rel = lambda d: d["releases"]["0.2.0"]  # noqa: E731
        sig = lambda d: rel(d)["x86_64"]["minisig"]  # noqa: E731
        raw = lambda d: base64.b64decode(sig(d)["signature"])  # noqa: E731
        cases = {
            "neither minisign nor unsigned": lambda d: rel(d).pop("minisign"),
            "both minisign and unsigned": lambda d: rel(d).update(unsigned="why"),
            "unsigned without a reason": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="")),
            "unsigned with a blank reason": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="  ")),
            "unsigned with a reason of two lines": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="a\nb")),
            "unsigned with a reason split by a carriage return": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="a\rb")),
            "unsigned with a reason split by a vertical tab": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="a\x0bb")),
            "unsigned with a reason split by NEL": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="a\x85b")),
            "unsigned with a reason split by a line separator": lambda d: (rel(d).pop("minisign"), rel(d)["x86_64"].pop("minisig"), rel(d).update(unsigned="a\u2028b")),
            "a trusted comment that is not utf-8": lambda d: sig(d).update(trusted_comment="x\ud800"),
            "a release without a build's minisig": lambda d: rel(d)["x86_64"].pop("minisig"),
            "a minisig on an unsigned release": lambda d: d["releases"]["0.1.0"]["x86_64"].update(minisig=sig(d)),
            "a key of another length": lambda d: rel(d)["minisign"].update(public_key=b64(b"Ed" + b"\1" * 39)),
            "a key that does not start Ed": lambda d: rel(d)["minisign"].update(public_key=b64(b"ED" + base64.b64decode(rel(d)["minisign"]["public_key"])[2:])),
            "a key that is not base64": lambda d: rel(d)["minisign"].update(public_key="RWTh!"),
            "a key id that is not the key's": lambda d: rel(d)["minisign"].update(key_id="E105681F92C28E5B"),
            "a key id in lower case": lambda d: rel(d)["minisign"].update(key_id="5b8ec2921f6805e1"),
            "no release_keys_commit": lambda d: rel(d)["minisign"].pop("release_keys_commit"),
            "a short release_keys_commit": lambda d: rel(d)["minisign"].update(release_keys_commit="b1b65cb"),
            "a signature of the legacy kind": lambda d: sig(d).update(signature=b64(b"Ed" + raw(d)[2:])),
            "a signature of 73 bytes": lambda d: sig(d).update(signature=b64(raw(d)[:-1])),
            "a signature by another key": lambda d: sig(d).update(signature=b64(raw(d)[:2] + b"\1" * 8 + raw(d)[10:])),
            "a signature that is not base64": lambda d: sig(d).update(signature="!!"),
            "a global signature of 63 bytes": lambda d: sig(d).update(global_signature=b64(base64.b64decode(sig(d)["global_signature"])[:-1])),
            "a trusted comment that is no string": lambda d: sig(d).update(trusted_comment=5),
            "an extra field": lambda d: sig(d).update(extra="x"),
            "a signature of neither kind": lambda d: sig(d).update(signature=b64(b"XX" + raw(d)[2:])),
            "a key id that is the signature's but not the key's": lambda d: (
                rel(d)["minisign"].update(key_id="0807060504030201"), sig(d).update(signature=b64(raw(d)[:2] + bytes.fromhex("0807060504030201")[::-1] + raw(d)[10:]))),
            "a global signature with padding bits set": lambda d: sig(d).update(global_signature=sig(d)["global_signature"][:-3] + "R=="),
        }
        control = json.loads(json.dumps(good))
        control["releases"]["0.2.0"].pop("minisign")
        control["releases"]["0.2.0"]["x86_64"].pop("minisig")
        control["releases"]["0.2.0"]["unsigned"] = "predates the key"
        self.assertIsNone(iw.pin_problem(control), "positive control: the same edit with a real reason is a valid pin")
        for label, mutate in cases.items():
            d = json.loads(json.dumps(good))
            mutate(d)
            problem = iw.pin_problem(d)
            self.assertIsNotNone(problem, label)
            if label.startswith("unsigned"):
                self.assertIn("unsigned", problem, label)
                self.assertNotIn("no build", problem, label)


class Signature(Case):
    def refused_before_extraction(self):
        """Install the archive as the pin on disk has it; the reply must be a failure that installed and extracted nothing."""
        r = self.install()
        self.assertEqual(r["status"], "failed", r)
        self.nothing_installed()
        return r["reason"]

    def test_a_signed_archive_installs_and_the_reply_gains_nothing(self):
        self.release()
        r = self.install()
        self.assertEqual(r["status"], "installed", r)
        self.assertEqual(sorted(r), ["client", "programs", "sha256", "status", "units", "version"])

    def test_one_byte_changed_in_the_archive_is_refused_though_its_digest_is_the_pins(self):
        art = self.release()
        changed = art[:-1] + bytes([art[-1] ^ 1])
        # The pin names the changed archive's digest: only the signature can tell it from the one that was signed.
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            pin = pin_for(changed)
            pin["releases"][VERSION]["x86_64"]["minisig"] = pin_for(art)["releases"][VERSION]["x86_64"]["minisig"]
            json.dump(pin, fh)
        self.artifact = changed
        self.assertRegex(self.refused_before_extraction(), r"^minisign check failed: the archive's signature does not verify with the pinned key; nothing was installed$")
        self.release()
        self.assertEqual(self.install()["status"], "installed", "positive control: the signed bytes")

    def test_another_key_is_refused_whether_it_wears_the_pinned_id_or_its_own(self):
        art = self.release()
        for label, key_id, expect in (("the pinned id", KEY_ID, "the archive's signature does not verify"),
                                      ("its own id", b"\x09" * 8, "signature made by another key than the release's")):
            pin = pin_for(art)
            pin["releases"][VERSION]["x86_64"]["minisig"] = minisig_for(art, f"{ROOT}.tar.gz", entropy=OTHER_FIXTURE_ENTROPY, key_id=key_id)
            with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
                json.dump(pin, fh)
            self.assertIn(expect, self.refused_before_extraction(), label)
        self.release()
        self.assertEqual(self.install()["status"], "installed", "positive control")

    def test_an_edited_trusted_comment_is_refused(self):
        art = self.release()
        pin = pin_for(art)
        pin["releases"][VERSION]["x86_64"]["minisig"]["trusted_comment"] += "\tx:1"
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin, fh)
        self.assertIn("the trusted comment's signature does not verify", self.refused_before_extraction())

    def test_a_signed_comment_that_names_another_file_is_refused(self):
        art = self.release()
        for comment in (COMMENT.format(name="other.tar.gz"), f"timestamp:1\tfile:{ROOT}.tar.gz.x\thashed",
                        f"timestamp:1\tnotfile:{ROOT}.tar.gz\thashed", f"timestamp:1 file:{ROOT}.tar.gz hashed"):
            pin = pin_for(art)
            pin["releases"][VERSION]["x86_64"]["minisig"] = minisig_for(art, f"{ROOT}.tar.gz", comment=comment)
            with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
                json.dump(pin, fh)
            self.assertIn(f"does not name file:{ROOT}.tar.gz", self.refused_before_extraction(), comment)

    def test_the_verifier_alone_refuses_a_signature_filed_under_another_key_id(self):
        art = b"archive"
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as d:
            path = os.path.join(d, "a")
            with open(path, "wb") as fh:
                fh.write(art)
            iw.minisign.verify_file(path, public_key_line(), minisig_for(art, "a"), "a")    # positive control
            with self.assertRaisesRegex(iw.minisign.SignatureError, "another key"):
                iw.minisign.verify_file(path, public_key_line(), minisig_for(art, "a", key_id=b"\x09" * 8), "a")

    def test_a_legacy_signature_is_refused(self):
        art = self.release()
        pin = pin_for(art)
        pin["releases"][VERSION]["x86_64"]["minisig"] = minisig_for(art, f"{ROOT}.tar.gz", kind=b"Ed")
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin, fh)
        self.assertIn("legacy signature (Ed)", self.refused_before_extraction())
        # And the verifier refuses it on its own, were a pin ever to let one through: the legacy signature is valid Ed25519 of the file.
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as d:
            path = os.path.join(d, "a")
            with open(path, "wb") as fh:
                fh.write(art)
            with self.assertRaisesRegex(iw.minisign.SignatureError, "legacy kind"):
                iw.minisign.verify_file(path, public_key_line(), minisig_for(art, "a", kind=b"Ed"), "a")

    def test_an_unsigned_current_release_is_refused_with_nothing_downloaded(self):
        art = self.release()
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin_for(art, signed=False), fh)
        r = self.install()
        self.assertEqual(r["status"], "refused", r)
        self.assertRegex(r["reason"], r"^0\.1\.0 is unsigned \(the fixture predates the key\) and an unsigned release is never installed; nothing was downloaded$")
        self.assertEqual((self.fetched, self.events), ([], []), "no lease, no download")
        self.nothing_installed()

    def test_an_unsigned_release_is_not_current_even_when_the_marker_names_it(self):
        art = self.release()
        self.assertEqual(self.install()["status"], "installed")
        with open(os.path.join(self.root, iw.PIN_REL), "w") as fh:
            json.dump(pin_for(art, signed=False), fh)
        self.assertEqual(self.install()["status"], "refused", "the signed install is not an answer for a pin that says unsigned")

    def test_fetch_and_unpack_alone_checks_the_signature_before_it_extracts(self):
        art = self.release()
        release, build = released(art)
        build["minisig"] = minisig_for(art, "another-name.tar.gz")
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            with self.assertRaisesRegex(iw.InstallError, "^minisign check failed: .*does not name file:"):
                iw.fetch_and_unpack(release, build, TOKEN, dest, self.fetch)
            self.assertEqual(os.listdir(dest), [], "nothing extracted and the part file removed")
        unsigned, build = released(art, signed=False)
        self.fetched.clear()
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            with self.assertRaisesRegex(iw.InstallError, "is unsigned"):
                iw.fetch_and_unpack(unsigned, build, TOKEN, dest, self.fetch)
        self.assertEqual(self.fetched, [], "nothing downloaded")

    def test_a_digest_mismatch_is_still_named_before_the_signature_is_looked_at(self):
        art = self.release()
        release, build = released(art)
        build["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(dir=self._tmp.name) as dest:
            with self.assertRaisesRegex(iw.InstallError, "^sha256 mismatch"):
                iw.fetch_and_unpack(release, build, TOKEN, dest, self.fetch)


@unittest.skipUnless(shutil.which("minisign"), "the minisign program is not installed here: the cross-check against it did not run")
class AgainstMinisign(Case):
    """The same bytes through the `minisign` program and through the verifier: neither is the oracle of the other alone."""

    def run_minisign(self, *argv, cwd):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": cwd, "LC_ALL": "C"}
        return subprocess.run(["minisign", *argv], cwd=cwd, env=env, capture_output=True, text=True, timeout=30, check=False)

    def keyed(self):
        d = tempfile.mkdtemp(dir=self._tmp.name)
        r = self.run_minisign("-G", "-W", "-p", "k.pub", "-s", "k.key", cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(d, "k.pub")) as fh:
            return d, fh.read().splitlines()[1]

    def signed_by_minisign(self, d, content: bytes, *flags):
        with open(os.path.join(d, "a.tar.gz"), "wb") as fh:
            fh.write(content)
        r = self.run_minisign("-S", *flags, "-s", "k.key", "-m", "a.tar.gz", "-x", "a.minisig", cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(d, "a.minisig")) as fh:
            lines = fh.read().splitlines()
        return {"signature": lines[1], "trusted_comment": lines[2].removeprefix("trusted comment: "), "global_signature": lines[3]}

    def test_a_signature_minisign_made_verifies_and_each_change_is_refused(self):
        d, key = self.keyed()
        content = os.urandom(4096)
        sig = self.signed_by_minisign(d, content)
        path = os.path.join(d, "a.tar.gz")
        iw.minisign.verify_file(path, key, sig, "a.tar.gz")      # does not raise: the positive control
        self.assertIsNone(iw.minisign.key_problem(key, iw.minisign.key_id_text(base64.b64decode(key)[2:10])))
        with open(path, "wb") as fh:
            fh.write(content[:-1] + bytes([content[-1] ^ 1]))
        with self.assertRaises(iw.minisign.SignatureError, msg="a byte of the file"):
            iw.minisign.verify_file(path, key, sig, "a.tar.gz")
        with open(path, "wb") as fh:
            fh.write(content)
        with self.assertRaises(iw.minisign.SignatureError):
            iw.minisign.verify_file(path, key, {**sig, "trusted_comment": sig["trusted_comment"] + "x"}, "a.tar.gz")
        with self.assertRaisesRegex(iw.minisign.SignatureError, "does not name file:b"):
            iw.minisign.verify_file(path, key, sig, "b")
        d2, key2 = self.keyed()
        with self.assertRaises(iw.minisign.SignatureError):
            iw.minisign.verify_file(path, key2, sig, "a.tar.gz")

    def test_minisign_legacy_signature_is_refused(self):
        d, key = self.keyed()
        sig = self.signed_by_minisign(d, b"legacy", "-l")
        self.assertTrue(base64.b64decode(sig["signature"]).startswith(b"Ed"), "the control: minisign wrote the legacy kind")
        self.assertIn("legacy", iw.minisign.minisig_problem(sig, iw.minisign.key_id_text(base64.b64decode(key)[2:10])))
        with self.assertRaises(iw.minisign.SignatureError):
            iw.minisign.verify_file(os.path.join(d, "a.tar.gz"), key, sig, "a.tar.gz")

    def test_a_signature_the_tests_made_verifies_under_minisign_and_a_changed_one_does_not(self):
        d = tempfile.mkdtemp(dir=self._tmp.name)
        content = b"cross-check"
        with open(os.path.join(d, "a.tar.gz"), "wb") as fh:
            fh.write(content)
        key_line = public_key_line()
        sig = minisig_for(content, "a.tar.gz")

        def check(sig_lines):
            first, comment, last = sig_lines.values()    # minisig_for's order, which the .minisig file's lines 2-4 follow
            with open(os.path.join(d, "a.minisig"), "w") as fh:
                fh.write(f"untrusted comment: x\n{first}\ntrusted comment: {comment}\n{last}\n")
            return self.run_minisign("-V", "-m", "a.tar.gz", "-x", "a.minisig", "-P", key_line, cwd=d)
        self.assertEqual(check(sig).returncode, 0, "minisign accepts the signer's output")
        self.assertNotEqual(check({**sig, "trusted_comment": sig["trusted_comment"] + "x"}).returncode, 0, "control: an edited comment")
        with open(os.path.join(d, "a.tar.gz"), "wb") as fh:
            fh.write(content + b"x")
        self.assertNotEqual(check(sig).returncode, 0, "control: an edited file")


class Read(Case):
    def read(self):
        return iw.installed(self.home, self.state, root=self.root, run=self.systemd)

    def test_nothing_installed_is_absent_with_the_units_said(self):
        self.release()
        got = self.read()
        got.pop("reserved_ports")                  # its own tests, below
        self.assertEqual(got, {"status": "absent", "units": {u: False for u in UNITS}, "client": {"status": "absent"}})

    def set_reserved(self, text):
        path = os.path.join(iw.PROC_ROOT, iw.RESERVED_PORTS_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def test_the_read_reports_whether_the_host_reserves_the_rosters_range(self):
        for text, status in (("47100-47199\n", "covered"), ("32768,47000-47150,47151-47300", "covered"), ("47100-47198", "not-covered"),
                             ("", "not-covered"), ("32768", "not-covered"), ("junk", "unreadable"), ("47100-", "unreadable")):
            self.set_reserved(text)
            got = self.read()["reserved_ports"]
            self.assertEqual((got["status"], got["range"]), (status, [47100, 47199]), text)
            self.assertEqual("reason" in got, status == "unreadable", text)
        os.unlink(os.path.join(iw.PROC_ROOT, iw.RESERVED_PORTS_REL))
        got = self.read()["reserved_ports"]
        self.assertEqual((got["status"], got["range"]), ("unreadable", [47100, 47199]))
        self.assertIn("cannot be read", got["reason"])

    def test_a_roster_without_a_range_leaves_the_reservation_unreadable_and_the_rest_of_the_read_alone(self):
        self.release()
        self.set_reserved("47100-47199")
        with open(os.path.join(self.root, iw.ROSTER_REL), "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "rows": []}, fh)
        got = self.read()
        self.assertEqual(got["reserved_ports"]["status"], "unreadable")
        self.assertNotIn("range", got["reserved_ports"])
        self.assertIn("port_range", got["reserved_ports"]["reason"])
        self.assertEqual(got["status"], "absent", "a positive control: the rest of the read is as without the problem")

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


class DownloadLease(Case):
    """The host's download turn: 28 accounts fetching 117 MB at once all hit their bound (2026-10-25)."""

    def test_the_download_waits_for_its_turn_and_gives_it_back_before_the_install_goes_on(self):
        self.release()
        self.assertEqual(self.install()["status"], "installed")
        ev = self.events
        self.assertEqual(ev[:3], [f"lease {iw.DOWNLOAD_LEASE} wait_s={iw.LEASE_WAIT_S}", "fetch", "release"],
                         "the turn is taken before the fetch and released once the archive is extracted")
        later = [e for e in ev[3:] if e.startswith("run ")]
        self.assertTrue(later, "positive control: the install did run commands after the turn")
        self.assertEqual(ev.count("release"), 1)
        self.assertLess(ev.index("release"), ev.index(later[0]), "not held through install.sh or the restart")

    def test_a_refused_turn_fetches_nothing_and_installs_nothing(self):
        self.release()
        self.lease_refused = iw.LeaseRefused(75, "fabric-lease: held", "held")
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("download lease stayed held", r["reason"])
        self.lease_refused = iw.LeaseRefused(2, "no lease directory at /run/lock/x", "nodir")
        self.assertIn("no lease directory at /run/lock/x", self.install()["reason"])
        self.assertEqual(self.fetched, [], "never queued-around")
        self.nothing_installed()

    def test_the_turn_is_given_back_when_the_download_fails(self):
        self.release()

        def broken(url, token, dest, **k):
            self.events.append("fetch")
            raise OSError(5, "boom")
        r = self.install(fetch=broken)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.events[-1], "release")

    def test_an_account_that_is_current_does_not_queue_for_a_download_it_will_not_make(self):
        self.release()
        self.install()
        self.events.clear()
        self.assertEqual(self.install()["status"], "current")
        self.assertEqual(self.events, [])

    def test_the_budget_covers_the_wait_for_a_turn(self):
        self.assertGreater(iw.CARRIER_INSTALL_BUDGET_S, iw.LEASE_WAIT_S + iw.DOWNLOAD_TIMEOUT_S)

    def test_the_real_lease_serialises_two_turns_under_its_own_name_not_the_claude_installs(self):
        import threading
        import time
        leases = os.path.join(self.root, "leases")
        os.makedirs(leases)
        repo = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        with unittest.mock.patch.dict(os.environ, {"AGENT_FABRIC_LEASES": leases, "AGENT_FABRIC_PYTHON": sys.executable}):
            first = iw.hold_lease(repo, wait_s=20, name=iw.DOWNLOAD_LEASE)
            other = iw.hold_lease(repo, wait_s=20, name="claude-install")      # another lease is not queued behind it
            other.release()
            got: list[float] = []
            t0 = time.monotonic()

            def second():
                turn = iw.hold_lease(repo, wait_s=20, name=iw.DOWNLOAD_LEASE)
                got.append(time.monotonic() - t0)
                turn.release()
            th = threading.Thread(target=second)
            th.start()
            time.sleep(1.5)
            self.assertEqual(got, [], "the second account waits while the first holds its turn")
            first.release()
            th.join(30)
        self.assertEqual(len(got), 1)
        self.assertGreaterEqual(got[0], 1.5)
        self.assertEqual(iw.DOWNLOAD_LEASE, "interweave-download")


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
            if os.path.basename(argv[0]) == "systemctl" and argv[2] == "show" and argv[3] == "--property=ActiveState" and self.systemd.restarts:
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

    def test_a_unit_that_is_active_on_a_replaced_file_is_not_a_restart(self):
        # install.sh renames over the old file, so `--version` of the file on disk is the new one even if the restart
        # never happened: only the process's own exe tells.
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.exe = os.path.join(self.bindir, "transport-daemon") + " (deleted)"
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("has been replaced", r["checks"][0]["reason"])
        self.assert_previous_back(old)

    def test_a_daemon_running_some_other_program_is_not_the_installed_one(self):
        self.release()
        self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.exe = "/usr/bin/sleep"
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("not the installed", r["checks"][0]["reason"])

    def test_a_daemon_without_a_main_process_fails_the_check(self):
        self.release()
        self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.main_pid = 0
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("no main process", r["checks"][0]["reason"])

    def test_a_second_failed_restore_does_not_replace_the_first_ones_kept_copies(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.after_restart[DAEMON_UNIT] = "failed"
        block = os.path.join(self.bindir, ".transport-daemon.restore", "x")
        os.makedirs(block)
        first = self.install()
        self.systemd.states = {DAEMON_UNIT: "active"}       # the first attempt left it failed
        second = self.install()
        self.assertEqual((first["restored"], second["restored"]), (False, False))
        kept = sorted(n for n in os.listdir(self.state) if n.startswith(f"{iw.INSTALL_OP}-previous."))
        self.assertEqual(len(kept), 2, "each attempt keeps its own")
        self.assertEqual(digest_of(os.path.join(self.state, kept[0], "transport-daemon")), old["transport-daemon"],
                         "the first attempt's copy is still the account's true previous program, the one whose restore failed")
        self.assertNotEqual(digest_of(os.path.join(self.state, kept[1], "transport-daemon")), old["transport-daemon"],
                            "the second attempt kept what the first left, not the first's copy")

    def test_a_program_that_was_a_link_is_a_link_again_even_over_a_killed_restores_leftover(self):
        self.release()
        self.seed_old()
        path = os.path.join(self.bindir, "transportctl")
        os.unlink(path)
        os.symlink("transport-daemon", path)
        with open(os.path.join(self.bindir, ".transportctl.restore"), "w") as fh:
            fh.write("stale")
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.after_restart[DAEMON_UNIT] = "failed"
        r = self.install()
        self.assertEqual((r["status"], r["restored"]), ("failed", True))
        self.assertEqual(os.readlink(path), "transport-daemon")

    def test_a_restore_that_cannot_finish_tries_every_program_keeps_the_copies_and_still_names_the_check(self):
        self.release()
        old = self.seed_old()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.systemd.after_restart[DAEMON_UNIT] = "failed"
        os.makedirs(os.path.join(self.bindir, ".transport-daemon.restore", "x"))      # in the way of that one program
        with open(os.path.join(self.bindir, ".transportctl.restore"), "w") as fh:     # a killed restore's leftover
            fh.write("stale")
        r = self.install()
        self.assertEqual((r["status"], r["restored"]), ("failed", False))
        self.assertIn("transport-daemon", r["reason"])
        self.assertEqual(digest_of(os.path.join(self.bindir, "transportctl")), old["transportctl"], "the other program was still put back")
        self.assertEqual(len(r["checks"]), 1, "the check that caused the rollback is in the reply")
        kept, = (os.path.join(self.state, n) for n in os.listdir(self.state) if n.startswith(f"{iw.INSTALL_OP}-previous."))
        self.assertIn(kept, r["reason"])
        self.assertEqual(sorted(os.listdir(kept)), sorted(old), "the old programs survive the work directory's removal")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)))

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

    def test_the_read_sees_a_reported_program_that_prints_another_version_whatever_the_daemon_does(self):
        self.release()
        self.install()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.assertEqual(self.read_channel()["status"], "ok")
        with open(os.path.join(self.bindir, "transportctl"), "wb") as fh:
            fh.write(program("transportctl", f"transportctl {VERSION}+deadbeef0000"))
        c = self.read_channel()
        self.assertEqual(c["status"], "off")
        self.assertIn("transportctl --version prints", c["reason"])

    def test_the_read_sees_a_daemon_that_never_restarted(self):
        self.release()
        self.install()
        self.systemd.states = {DAEMON_UNIT: "active"}
        self.assertEqual(self.read_channel()["status"], "ok")
        self.systemd.exe = os.path.join(self.bindir, "transport-daemon") + " (deleted)"
        c = self.read_channel()
        self.assertEqual(c["status"], "off")
        self.assertIn("has been replaced", c["reason"])

    def test_a_manager_that_stops_answering_mid_check_is_unknown_not_off(self):
        self.release()
        self.install()
        self.systemd.states = {DAEMON_UNIT: "active"}
        real = self.systemd.__call__
        seen = []

        def stalls(argv, **kw):
            if os.path.basename(argv[0]) == "systemctl" and argv[2] == "show":
                seen.append(argv)
                if len(seen) > 2:                      # the two state queries of running_units answered
                    raise subprocess.TimeoutExpired(argv, 1)
            return real(argv, **kw)
        c = iw.installed(self.home, self.state, root=self.root, run=stalls)["channel"]
        self.assertEqual(c["status"], "unknown")

    def read_channel(self):
        return iw.installed(self.home, self.state, root=self.root, run=self.systemd)["channel"]


class ClientProgram(Case):
    """Step 12 of the install and the read's `client` (agent-fabric ADR-064 rule 5)."""

    def target(self):
        return os.path.join(self.home, iw.CLIENT_PROGRAM_REL)

    def read(self):
        return iw.installed(self.home, self.state, root=self.root, run=self.systemd)

    def test_a_current_account_without_the_program_gets_it_and_the_reply_says_so(self):
        self.release()
        self.assertEqual(self.install()["client"], "installed")
        os.unlink(self.target())
        before = len(self.fetched)
        r = self.install()
        self.assertEqual((r["status"], r["client"]), ("current", "installed"), "current means the archive, not the client program")
        self.assertEqual(len(self.fetched), before, "nothing was downloaded for it")
        with open(self.target(), "rb") as fh:
            self.assertEqual(fh.read(), CLIENT_BYTES)
        self.assertEqual(stat.S_IMODE(os.stat(self.target()).st_mode), 0o755)
        self.assertEqual(self.install()["client"], "already")

    def test_an_edited_copy_is_replaced_and_the_read_shows_each_state(self):
        self.release()
        self.assertEqual(self.read()["client"], {"status": "absent"})
        self.install()
        self.assertEqual(self.read()["client"], {"status": "ok"})
        with open(self.target(), "ab") as fh:
            fh.write(b"# edited\n")
        self.assertEqual(self.read()["client"], {"status": "differs"})
        self.assertEqual(self.install()["client"], "installed")
        self.assertEqual(self.read()["client"], {"status": "ok"})
        os.chmod(self.target(), 0o644)
        self.assertEqual(self.read()["client"], {"status": "differs"}, "the mode is part of being the clone's")

    def test_a_source_that_cannot_be_read_is_unreadable_never_absent_or_ok(self):
        self.release()
        self.install()
        os.unlink(os.path.join(self.root, "runtime", "interweave", "client"))
        got = self.read()["client"]
        self.assertEqual(got["status"], "unreadable")
        self.assertIn("runtime/interweave/client", got["reason"])

    def test_a_program_that_cannot_be_inspected_is_unreadable_not_absent(self):
        self.release()
        self.install()
        d = os.path.dirname(self.target())
        os.chmod(d, 0)
        self.addCleanup(os.chmod, d, 0o755)
        if os.geteuid() == 0:
            self.skipTest("root searches any directory")
        got = self.read()["client"]
        self.assertEqual(got["status"], "unreadable")
        self.assertIn("client", got["reason"])
        os.chmod(d, 0o755)
        self.assertEqual(self.read()["client"], {"status": "ok"}, "positive control: searchable again")
        os.unlink(self.target())
        self.assertEqual(self.read()["client"], {"status": "absent"}, "a missing file is still absent")

    def test_a_program_file_that_cannot_be_read_is_unreadable_not_differs(self):
        self.release()
        self.install()
        os.chmod(self.target(), 0)
        if os.geteuid() == 0:
            self.skipTest("root reads any file")
        self.assertEqual(self.read()["client"]["status"], "unreadable")
        os.chmod(self.target(), 0o755)
        self.assertEqual(self.read()["client"], {"status": "ok"}, "positive control")

    def test_a_copy_that_cannot_be_made_fails_the_reply_and_the_next_run_retries_it(self):
        self.release()
        os.makedirs(self.target())          # a directory where the file goes: os.replace refuses it
        r = self.install()
        self.assertEqual((r["status"], r["client"]), ("failed", "failed"))
        self.assertIn("client unit's program", r["reason"])
        self.assertEqual(self.installed_names(), sorted(PROGRAMS), "the programs stayed as installed")
        self.assertFalse([n for n in os.listdir(os.path.dirname(self.target())) if n.startswith(".client.")], "no temporary file survives")
        os.rmdir(self.target())
        r = self.install()
        self.assertEqual((r["status"], r["client"]), ("current", "installed"))

    def test_a_failed_install_does_not_touch_the_program(self):
        self.release()
        self.lease_refused = iw.LeaseRefused(75, "fabric-lease: held", "held")
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("client", r)
        self.assertFalse(os.path.lexists(self.target()))


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
               "carrier_install_opts": {"state": self.state, "fetch": self.fetch, "lease": self.lease, "token": lambda n: TOKEN, "machine": "x86_64"},
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
        rows = [{"account": "a", "status": "ok", "interweaveInstall": {"status": "installed", "version": VERSION, "sha256": "ab" * 32,
                                                          "units": {"running_before": [], "check": "not run: no unit was running"}},
                 "interweave": {"status": "ok", "version": VERSION, "pinned": True, "units": {u: True for u in UNITS},
                                "channel": {"status": "off", "reason": "status exited 3"}}},
                {"account": "b", "status": "no answer"},
                {"account": "c", "status": "ok", "interweaveInstall": {"status": "failed", "version": VERSION,
                                                                          "reason": "sha256 mismatch: x\u0007"},
                 "interweave": {"status": "absent", "units": {u: False for u in UNITS}}}]
        install = ctl.table("interweave-install", rows).split("\n")
        self.assertRegex(install[1], r"^a +installed +0\.1\.0 +abababababab")
        self.assertIn("units: not run: no unit was running", install[1], "the news on an installed row")
        self.assertEqual(install[2].split()[:2], ["b", "no"])
        self.assertIn("sha256 mismatch", install[3])
        self.assertNotIn("\u0007", install[3], "an account's words reach the terminal escaped")
        read = ctl.table("interweave", rows).split("\n")
        self.assertRegex(read[1], r"^a +ok +0\.1\.0 +yes +both +off +status exited 3", "an account off the channel is not a clean row")
        self.assertRegex(read[3], r"^c +absent +- +- +no")
        self.assertIn("installed", ctl.ACTION_OK["interweave-install"])
        self.assertIn("current", ctl.ACTION_OK["interweave-install"])
        self.assertNotIn("failed", ctl.ACTION_OK["interweave-install"])
        self.assertNotIn("refused", ctl.ACTION_OK["interweave-install"])


class UnitSystemd(Systemd):
    """Adds to the manager what a start and a stop ask of it: `enable --now`, `disable --now`, loginctl and the carrier's
    render-config. Every unit is knocked down by `disable` unless it is in `stuck`."""

    def __init__(self):
        super().__init__()
        self.linger = "yes"                    # loginctl's answer; None: loginctl cannot be run; "hang": it never answers
        self.render_rc = 0
        self.render_err = ""
        self.rendered: list[str] = []
        self.rendered_stdout = 0                # renders asked for on stdout, the read of a running pair
        self.roster_text = "config\n"           # what the carrier renders from the roster now
        self.enabled: list[str] = []
        self.disabled: list[str] = []
        self.enable_rc: dict[str, int] = {}
        self.disable_rc: dict[str, int] = {}
        self.after_enable: dict[str, str] = {}  # unit -> the state it reaches (default active)
        self.stuck: set[str] = set()            # units that stay active after a disable
        self.on_enable = None
        self.restarted: list[str] = []

    def __call__(self, argv, **kw):
        name = os.path.basename(argv[0])
        if name == "loginctl":
            self.calls.append(list(argv))
            if self.linger is None:
                raise FileNotFoundError("loginctl")
            if self.linger == "hang":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return subprocess.CompletedProcess(argv, 0, f"{self.linger}\n", "")
        if name == "gzcoord-carrier" and argv[1] == "render-config" and len(argv) == 2:
            self.calls.append(list(argv))
            self.rendered_stdout += 1
            return subprocess.CompletedProcess(argv, self.render_rc, self.roster_text if self.render_rc == 0 else "", self.render_err)
        if name == "gzcoord-carrier" and argv[1] == "render-config":
            self.calls.append(list(argv))
            if self.render_rc == 0:
                os.makedirs(os.path.dirname(argv[3]), exist_ok=True)
                with open(argv[3], "w") as fh:
                    fh.write(self.roster_text)
            self.rendered.append(argv[3])
            return subprocess.CompletedProcess(argv, self.render_rc, "", self.render_err)
        if name == "systemctl" and argv[2] == "restart":
            self.calls.append(list(argv))
            self.restarted.append(argv[3])
            self.states[argv[3]] = "active"
            return subprocess.CompletedProcess(argv, 0, "", "")
        if name == "systemctl" and argv[2] in ("enable", "disable"):
            self.calls.append(list(argv))
            unit = argv[-1]
            assert argv[3] == "--now", argv
            if argv[2] == "enable":
                self.enabled.append(unit)
                if self.on_enable:
                    self.on_enable(unit)
                if self.enable_rc.get(unit):
                    return subprocess.CompletedProcess(argv, self.enable_rc[unit], "", "Failed to enable unit: nope\n")
                self.states[unit] = self.after_enable.get(unit, "active")
            else:
                self.disabled.append(unit)
                if self.disable_rc.get(unit):
                    return subprocess.CompletedProcess(argv, self.disable_rc[unit], "", "")
                if unit not in self.stuck:
                    self.states[unit] = "inactive"
            return subprocess.CompletedProcess(argv, 0, "", "")
        return super().__call__(argv, **kw)


class StartStop(Case):
    def setUp(self):
        super().setUp()
        self.systemd = UnitSystemd()
        self.systemd.proc = os.path.join(self._tmp.name, "proc")
        self.systemd.bindir = os.path.join(self.home, ".local", "bin")
        self.release()
        self.assertEqual(self.install()["status"], "installed", "the account has the pin's programs and both templates")
        self.client_program = os.path.join(self.home, iw.CLIENT_PROGRAM_REL)
        with open(self.client_program, "rb") as fh:
            self.assertEqual(fh.read(), CLIENT_BYTES, "the install put the clone's client program in place")
        self.systemd.calls.clear()
        self.events.clear()
        self.reserve("47100-47199")

    def reserve(self, text):
        path = os.path.join(iw.PROC_ROOT, iw.RESERVED_PORTS_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text + "\n")

    def start(self, request=None, **kw):
        opts = dict(root=self.root, home=self.home, state=self.state, machine="x86_64", run=self.systemd, sleep=lambda s: None, login="agent",
                    lease=self.lease)
        opts.update(kw)
        return iw.carrier_start({} if request is None else request, **opts)

    def stop(self, request=None, **kw):
        opts = dict(root=self.root, home=self.home, state=self.state, run=self.systemd, sleep=lambda s: None)
        opts.update(kw)
        return iw.carrier_stop({} if request is None else request, **opts)

    def config(self):
        return iw.config_path(self.home, "gzcoord")

    def nothing_touched(self, why=""):
        self.assertEqual(self.systemd.rendered, [], why)
        self.assertEqual(self.systemd.enabled, [], why)
        self.assertEqual(self.systemd.disabled, [], why)
        self.assertFalse(os.path.exists(self.config()), why)

    def test_a_daemon_that_stays_activating_is_named_by_its_substate_exit_and_journal(self):
        self.systemd.after_enable[DAEMON_UNIT] = "activating"
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("after 5 look(s) (SubState auto-restart, Result exit-code, ExecMainStatus 1, NRestarts 7; "
                      "journal: transport-daemon: cannot bind 127.0.0.1:47130: address in use)", r["reason"])
        self.assertTrue(r["stopped"], "the diagnosis does not keep the units from being taken down")

    def tcp_table(self, *rows, v6=()):
        d = os.path.join(iw.PROC_ROOT, "net")
        os.makedirs(d, exist_ok=True)
        head = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        for name in ("tcp", "tcp6"):
            with open(os.path.join(d, name), "w") as fh:
                fh.write(head + "".join(rows if name == "tcp" else v6))

    def roster_row(self, login, port):
        path = os.path.join(self.root, iw.ROSTER_REL)
        with open(path) as fh:
            d = json.load(fh)
        d["rows"].append({"login": login, "port": port})
        with open(path, "w") as fh:
            json.dump(d, fh)

    def test_a_start_whose_port_is_held_by_an_older_connection_is_refused_before_anything_is_touched(self):
        self.roster_row("agent", 47130)
        self.tcp_table("   0: 0100007F:B81A 0100007F:0016 01 00000000:00000000 02:000957A2 00000000  1000        0 440987 2\n")
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn("local port 47130 is in use by a ESTABLISHED connection of uid 1000", r["reason"])
        self.nothing_touched()
        # the positive control: the same table without that socket, and one on a port that is not the account's, start
        self.tcp_table("   0: 0100007F:B81B 0100007F:0016 01 00000000:00000000 02:000957A2 00000000  1000        0 440987 2\n")
        self.assertEqual(self.start()["status"], "started")

    def test_a_daemon_that_runs_holds_its_own_port_and_the_start_goes_on(self):
        self.roster_row("agent", 47130)
        listen = "   0: 0100007F:B81A 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 440987 2\n"
        peer = "   1: 0100007F:B81A 0100007F:9999 01 00000000:00000000 00:00000000 00000000  1000        0 440988 2\n"
        self.tcp_table(listen, peer)
        self.systemd.states[DAEMON_UNIT] = "active"
        r = self.start()
        self.assertEqual(r["status"], "started", r)
        self.assertEqual(self.systemd.restarted, [DAEMON_UNIT], "the half-running pair is still restarted after the render")
        # the positive control: the same table with only the client running is a start that must bind, and is refused
        self.systemd.states = {CLIENT_UNIT: "active"}
        self.assertEqual(self.start()["status"], "refused")

    def test_a_daemon_that_is_only_activating_does_not_excuse_a_held_port(self):
        self.roster_row("agent", 47130)
        self.tcp_table("   0: 0100007F:B81A 0100007F:0016 01 00000000:00000000 02:000957A2 00000000  1000        0 440987 2\n")
        self.systemd.states[DAEMON_UNIT] = "activating"
        r = self.start()
        self.assertEqual(r["status"], "refused", r)
        self.assertIn("local port 47130 is in use", r["reason"])
        self.assertEqual(self.systemd.restarted, [], "nothing was restarted")
        self.assertEqual(self.systemd.rendered, [], "nothing was rendered")

    def test_a_port_held_on_the_ipv6_table_is_refused_too(self):
        self.roster_row("agent", 47130)
        self.tcp_table(v6=("   0: 00000000000000000000000001000000:B81A 00000000000000000000000001000000:0016 01 00000000:00000000 02:0009 00000000  1000        0 1 2\n",))
        self.assertEqual(self.start()["status"], "refused")

    def test_an_unreadable_connection_table_is_not_a_refusal(self):
        self.roster_row("agent", 47130)
        self.assertFalse(os.path.exists(os.path.join(iw.PROC_ROOT, "net", "tcp")))
        self.assertEqual(self.start()["status"], "started")

    def test_a_diagnosis_that_cannot_be_read_says_so_and_the_failure_stands(self):
        self.systemd.after_enable[DAEMON_UNIT] = "activating"
        self.systemd.props = ""
        self.systemd.journal_rc = 1
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("(its properties could not be read; journal: no lines readable)", r["reason"])
        self.systemd.hang = "journal"
        self.assertIn("journal: no lines readable", self.start()["reason"], "a journal that hangs is a bounded wait, not a hang")

    def test_a_start_renders_then_enables_the_daemon_then_the_client_and_checks_the_channel(self):
        r = self.start()
        self.assertEqual(r, {"status": "started", "units": {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}, "check": "passed"})
        self.assertEqual(self.systemd.rendered, [self.config()])
        self.assertTrue(self.config().endswith(os.path.join(".config", "interweave", "profiles", "gzcoord", "config.yaml")))
        self.assertEqual(self.systemd.enabled, [DAEMON_UNIT, CLIENT_UNIT], "daemon first")
        seq = [os.path.basename(c[0]) if c[0] != "systemctl" else c[2] for c in self.systemd.calls]
        seq = [("render" if c[1] == "render-config" else "status") if os.path.basename(c[0]) == "gzcoord-carrier" else x for c, x in zip(self.systemd.calls, seq)]
        self.assertLess(seq.index("loginctl"), seq.index("render"), "the linger question before anything is written")
        self.assertLess(seq.index("render"), seq.index("enable"), "config before units")
        self.assertLess(seq.index("enable"), seq.index("status"))
        self.assertGreater(self.systemd.status_calls, 0, "the carrier was asked its status")
        self.assertFalse(os.path.exists(os.path.join(self.state, iw.WORK)))

    def test_the_request_takes_no_argument(self):
        for args in ({"profile": "x"}, {"path": "/tmp/x"}, ["x"], "x", 0):
            for op in (self.start, self.stop):
                r = op({"args": args})
                self.assertEqual(r["status"], "refused", (op.__name__, args))
                self.assertIn("takes no argument", r["reason"])
        self.nothing_touched()
        for ok in ({}, {"args": None}, {"args": {}}):
            self.assertEqual(self.start(ok)["status"], "started", f"positive control {ok}")
            self.assertEqual(self.stop(ok)["status"], "stopped")

    def test_an_account_without_linger_is_refused_before_anything_is_written_or_started(self):
        for linger, said in (("no", "has no linger"), ("hang", "could not be asked"), (None, "could not be asked"), ("maybe", "could not be read")):
            self.systemd.linger = linger
            r = self.start()
            self.assertEqual(r["status"], "refused", linger)
            self.assertIn(said, r["reason"], linger)
            self.nothing_touched(f"linger={linger}")
        self.systemd.linger = "yes"
        self.assertEqual(self.start()["status"], "started", "positive control: the same account lingering")

    def test_no_valid_roster_row_is_a_refusal_and_a_render_that_breaks_a_failure_neither_starting_a_unit(self):
        self.systemd.render_rc, self.systemd.render_err = 2, "gzcoord-carrier: this agent has no valid row in the roster: nothing to render\n"
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn("no valid row in the roster", r["reason"])
        self.assertEqual((self.systemd.enabled, self.systemd.disabled), ([], []))
        self.assertFalse(os.path.exists(self.config()))
        self.systemd.render_rc, self.systemd.render_err = 1, "boom\n"
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertEqual((self.systemd.enabled, self.systemd.disabled), ([], []))
        self.systemd.render_rc = 0
        self.assertEqual(self.start()["status"], "started", "positive control")

    def test_the_render_is_taken_in_turn_on_the_host_lease_and_released_before_the_units_start(self):
        def logged(argv, **kw):
            if os.path.basename(argv[0]) == "gzcoord-carrier":
                self.events.append("render")
            elif "enable" in argv:
                self.events.append("enable")
            return self.systemd(argv, **kw)
        self.assertEqual(self.start(run=logged)["status"], "started")
        self.assertEqual(self.events[:4], [f"lease {iw.RENDER_LEASE} wait_s={iw.RENDER_LEASE_WAIT_S}", "render", "release", "enable"],
                         "held for the render alone, not through the units' start")

    def test_a_render_that_times_out_still_gives_the_turn_back(self):
        def slow(argv, **kw):
            if os.path.basename(argv[0]) == "gzcoord-carrier" and argv[1] == "render-config":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return self.systemd(argv, **kw)
        r = self.start(run=slow)
        self.assertEqual(r["status"], "failed")
        self.assertIn("did not finish", r["reason"])
        self.assertEqual(self.events, [f"lease {iw.RENDER_LEASE} wait_s={iw.RENDER_LEASE_WAIT_S}", "release"])

    def test_a_lease_held_or_unavailable_renders_nothing(self):
        self.lease_refused = iw.LeaseRefused(75, "fabric-lease: held", iw.LEASE_HELD)
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("render lease stayed held", r["reason"])
        self.lease_refused = iw.LeaseRefused(2, "no lease directory", "unavailable")
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("render queue is unavailable", r["reason"])
        self.nothing_touched()
        self.lease_refused = None
        self.assertEqual(self.start()["status"], "started", "positive control")

    def test_a_host_that_does_not_reserve_the_rosters_ports_is_refused_naming_the_setting(self):
        for text in ("", "47100-47150", "47101-47199", "32768", "47100-47150,47152-47199", "junk", "47100-"):
            self.reserve(text)
            r = self.start()
            self.assertEqual(r["status"], "refused", text)
            self.assertIn("ip_local_reserved_ports", r["reason"], text)
            self.assertIn("47100-47199", r["reason"], text)
            self.assertIn("`fabric-host <host> persist`", r["reason"], text)
            self.assertNotIn("set net.ipv4", r["reason"], "the fix is provisioning's, not a hand sysctl")
            self.nothing_touched(text)
            self.assertEqual(self.events, [], "no turn is taken for a host that will be refused")
        os.unlink(os.path.join(iw.PROC_ROOT, iw.RESERVED_PORTS_REL))
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn("cannot be read", r["reason"])
        for text in ("47100-47199", "47000-47300", "47100-47150,47151-47199", "47100-47199,50000", "47100-47120\n47121-47199"):
            self.reserve(text)
            self.assertEqual(self.start()["status"], "started", text)
            self.stop()

    def test_a_roster_without_a_usable_port_range_fails_the_start_touching_nothing(self):
        roster = os.path.join(self.root, iw.ROSTER_REL)
        for rng in (None, [47100], [47199, 47100], [47100, "47199"], [0, 47199], "47100-47199"):
            with open(roster, "w") as fh:
                json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", **({} if rng is None else {"port_range": rng}), "rows": []}, fh)
            r = self.start()
            self.assertEqual(r["status"], "failed", rng)
            self.assertIn("port_range", r["reason"], rng)
            self.nothing_touched(str(rng))
            self.assertEqual(self.events, [])
        with open(roster, "w") as fh:
            fh.write("{")
        self.assertEqual(self.start()["status"], "failed")
        with open(roster, "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "port_range": [47100, 47199], "rows": []}, fh)
        self.assertEqual(self.start()["status"], "started", "positive control")

    def test_a_running_pair_needs_the_render_lease_for_its_read_but_not_the_reservation(self):
        self.assertEqual(self.start()["status"], "started")
        self.events.clear()
        self.reserve("")
        r = self.start()
        self.assertEqual((r["status"], r.get("already_running")), ("started", True))
        self.assertEqual(self.events, [f"lease {iw.RENDER_LEASE} wait_s={iw.RENDER_LEASE_WAIT_S}", "release"], "the read queues like every render; no port check")

    def test_programs_that_are_not_the_pins_or_templates_that_are_missing_are_refused(self):
        with open(os.path.join(self.bindir, "transportctl"), "wb") as fh:
            fh.write(program("transportctl", f"transportctl {VERSION}+deadbeef0000"))
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn("not the pin's", r["reason"])
        self.nothing_touched("a program that prints another version")
        with open(os.path.join(self.bindir, "transportctl"), "wb") as fh:
            fh.write(program("transportctl"))
        os.unlink(os.path.join(iw.unit_dir(self.home), UNITS[1]))
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn(UNITS[1], r["reason"])
        self.nothing_touched("a missing template")
        shutil.copy(os.path.join(iw.unit_dir(self.home), UNITS[0]), os.path.join(iw.unit_dir(self.home), UNITS[1]))
        self.assertEqual(self.start()["status"], "started", "positive control")
        shutil.rmtree(self.bindir)
        self.assertEqual(self.start()["status"], "refused", "no programs at all")

    def test_a_missing_client_program_is_refused_before_the_daemon_is_started(self):
        os.chmod(self.client_program, 0o644)
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn(self.client_program, r["reason"])
        self.assertIn(f"run {iw.INSTALL_OP}", r["reason"], "the refusal names a remedy that exists")
        self.assertNotIn("bootstrap", r["reason"])
        self.nothing_touched("a client program that is not executable")
        os.unlink(self.client_program)
        self.assertEqual(self.start()["status"], "refused", "absent")
        self.nothing_touched("a client program that is absent")
        os.symlink("/bin/true", self.client_program)
        self.assertEqual(self.start()["status"], "started", "positive control")

    def test_a_refused_enable_names_the_failure_not_the_symlink_it_printed_first(self):
        def enable(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, "", "Job failed: see journalctl\nCreated symlink /a -> /b.\n")
        self.assertIn("Job failed", iw._systemctl(["enable", "--now", "u"], enable, self.home))

    def test_a_unit_that_does_not_come_up_stops_both_and_says_failed(self):
        for label, setup in (("the daemon dies", lambda: self.systemd.after_enable.update({DAEMON_UNIT: "failed"})),
                             ("the client dies", lambda: self.systemd.after_enable.update({CLIENT_UNIT: "inactive"})),
                             ("enable of the client is refused", lambda: self.systemd.enable_rc.update({CLIENT_UNIT: 1})),
                             ("the carrier does not answer", lambda: setattr(self.systemd, "status_rcs", [3]))):
            self.systemd.states.clear()
            self.systemd.after_enable.clear(); self.systemd.enable_rc.clear(); self.systemd.status_rcs = [0]
            self.systemd.disabled.clear(); self.systemd.enabled.clear()
            setup()
            r = self.start()
            self.assertEqual(r["status"], "failed", label)
            self.assertTrue(r["stopped"], label)
            self.assertIn("both units are stopped", r["reason"], label)
            self.assertEqual(sorted(self.systemd.disabled), sorted([DAEMON_UNIT, CLIENT_UNIT]), f"{label}: both taken down, whichever one was the trouble")
            self.assertLessEqual(set(r["units"].values()), {"inactive", "failed"}, label)
            self.assertEqual(r["checks"][0]["status"], "failed", label)

    def test_a_failed_start_that_cannot_stop_what_it_started_says_so(self):
        self.systemd.after_enable[CLIENT_UNIT] = "failed"
        self.systemd.stuck = {DAEMON_UNIT}
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIs(r["stopped"], False)
        self.assertIn("may still run", r["reason"])
        self.assertEqual(r["units"][DAEMON_UNIT], "active")
        self.systemd.stuck = set()
        self.systemd.disable_rc = {CLIENT_UNIT: 1}
        self.systemd.states.clear()
        r = self.start()
        self.assertIs(r["stopped"], False, "a disable that exits non-zero is not a stop even when the unit is inactive")

    def test_a_carrier_that_is_slow_to_open_its_socket_is_waited_for_but_not_for_ever(self):
        self.systemd.status_rcs = [3] * (iw.STARTUP_STATUS_POLLS - 1) + [0]
        r = self.start()
        self.assertEqual(r["status"], "started", "answering on the last look is an answer")
        self.assertEqual(self.systemd.status_calls, iw.STARTUP_STATUS_POLLS)
        self.systemd.status_calls = 0
        self.systemd.status_rcs = [3] * iw.STARTUP_STATUS_POLLS + [0]
        os.unlink(self.config())
        self.systemd.states.clear()
        r = self.start()
        self.assertEqual(r["status"], "failed", "one look beyond the bound")
        self.assertEqual(self.systemd.status_calls, iw.STARTUP_STATUS_POLLS)

    def test_with_both_units_running_and_the_config_current_a_start_changes_nothing_and_still_checks(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.rendered.clear(); self.systemd.enabled.clear(); self.systemd.restarted.clear()
        r = self.start()
        self.assertEqual((r["status"], r["already_running"], r["check"]), ("started", True, "passed"))
        self.assertNotIn("rerendered", r)
        self.assertEqual((self.systemd.rendered, self.systemd.enabled, self.systemd.restarted), ([], [], []), "a current file is not rewritten")
        self.assertEqual(self.systemd.rendered_stdout, 1, "but the roster was read: that is how a change is found")
        self.systemd.exe = "/tmp/other"
        r = self.start()
        self.assertEqual(r["status"], "failed", "already running is not already well: the daemon's process is checked")
        self.assertTrue(r["stopped"])

    def test_with_both_units_running_a_roster_change_replaces_the_config_and_restarts_both(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        self.systemd.roster_text = "config with a new peer\n"
        r = self.start()
        self.assertEqual((r["status"], r["check"], r.get("rerendered")), ("started", "passed", True))
        self.assertNotIn("already_running", r, "something was changed")
        with open(self.config()) as fh:
            self.assertEqual(fh.read(), "config with a new peer\n")
        self.assertEqual(self.systemd.restarted, [DAEMON_UNIT, CLIENT_UNIT])
        self.assertEqual(stat.S_IMODE(os.stat(self.config()).st_mode), 0o600)
        self.systemd.restarted.clear()
        self.assertTrue(self.start()["already_running"], "the second start finds the file current")
        self.assertEqual(self.systemd.restarted, [])

    def test_with_both_units_running_a_missing_config_is_written_and_the_pair_restarted(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        os.unlink(self.config())
        self.assertTrue(self.start()["rerendered"])
        self.assertTrue(os.path.exists(self.config()))
        self.assertEqual(self.systemd.restarted, [DAEMON_UNIT, CLIENT_UNIT])

    def test_with_both_units_running_a_render_that_fails_leaves_file_and_units_alone(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        self.systemd.roster_text = "changed\n"
        self.systemd.render_rc, self.systemd.render_err = 2, "gzcoord-carrier: no valid row\n"
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertIn("still run on the previous config.yaml", r["reason"])
        self.assertEqual(sorted(r["units"]), [CLIENT_UNIT, DAEMON_UNIT])
        self.assertEqual(self.systemd.restarted, [])
        with open(self.config()) as fh:
            self.assertEqual(fh.read(), "config\n")
        self.systemd.render_rc = 1
        self.assertEqual(self.start()["status"], "failed")
        self.assertEqual(self.systemd.restarted, [])

    def test_with_both_units_running_a_lease_that_stays_held_says_the_units_still_run(self):
        self.assertEqual(self.start()["status"], "started")
        self.lease_refused = iw.LeaseRefused(75, "fabric-lease: held", iw.LEASE_HELD)
        r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("still run on the previous config.yaml", r["reason"])
        self.assertEqual(sorted(r["units"]), [CLIENT_UNIT, DAEMON_UNIT])
        self.assertNotIn("nothing was started", r["reason"])

    def test_with_both_units_running_a_config_that_cannot_be_written_restarts_nothing(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        self.systemd.roster_text = "changed\n"
        with unittest.mock.patch.object(iw.roster, "write_config", side_effect=PermissionError("no")):
            r = self.start()
        self.assertEqual(r["status"], "failed")
        self.assertIn("still run on the previous config.yaml", r["reason"])
        self.assertEqual(sorted(r["units"]), [CLIENT_UNIT, DAEMON_UNIT], "the units' states are in the reply")
        self.assertEqual(self.systemd.restarted, [])

    def test_with_both_units_running_a_changed_config_needs_the_reservation_before_the_restart(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        self.systemd.roster_text = "changed\n"
        self.reserve("")
        r = self.start()
        self.assertEqual(r["status"], "refused")
        self.assertEqual(self.systemd.restarted, [])
        with open(self.config()) as fh:
            self.assertEqual(fh.read(), "config\n")

    def test_with_both_units_running_an_unreadable_port_range_is_a_failure_that_restarts_nothing(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.restarted.clear()
        self.systemd.roster_text = "changed\n"
        with open(os.path.join(self.root, iw.ROSTER_REL), "w") as fh:
            json.dump({"version": 1, "profile": "gzcoord", "endpoint": "gzcoord", "rows": []}, fh)
        r = self.start()
        self.assertEqual(r["status"], "failed", "an unreadable roster fails, as on the path that starts the pair")
        self.assertIn("still run on the previous config.yaml", r["reason"])
        self.assertEqual(self.systemd.restarted, [])

    def test_with_both_units_running_a_restart_the_manager_refuses_stops_both(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.roster_text = "changed\n"
        orig = self.systemd.__call__
        def refuse(argv, **kw):
            if argv[:3] == ["systemctl", "--user", "restart"]:
                return subprocess.CompletedProcess(argv, 1, "", "Failed\n")
            return orig(argv, **kw)
        r = self.start(run=refuse)
        self.assertEqual(r["status"], "failed")
        self.assertTrue(r["stopped"], "the relay carries alone (rule 11)")

    def test_with_one_unit_running_the_start_goes_the_whole_way(self):
        self.systemd.states = {CLIENT_UNIT: "active"}
        r = self.start()
        self.assertEqual(r["status"], "started")
        self.assertNotIn("already_running", r)
        self.assertEqual(self.systemd.enabled, [DAEMON_UNIT, CLIENT_UNIT])
        self.assertEqual(self.systemd.restarted, [CLIENT_UNIT], "a unit that ran read the old config.yaml")

    def test_with_only_the_daemon_running_it_is_restarted_after_the_render_so_it_reads_the_new_config(self):
        self.systemd.states = {DAEMON_UNIT: "active"}
        r = self.start()
        self.assertEqual(r["status"], "started")
        self.assertEqual(self.systemd.restarted, [DAEMON_UNIT])
        self.assertEqual(self.systemd.enabled, [DAEMON_UNIT, CLIENT_UNIT])
        self.systemd.restarted.clear()
        self.assertTrue(self.start()["already_running"])
        self.assertEqual(self.systemd.restarted, [], "both running: nothing restarted")

    def test_a_restart_the_manager_refuses_stops_both_and_says_failed(self):
        self.systemd.states = {DAEMON_UNIT: "active"}
        orig = self.systemd.__call__
        def refusing(argv, **kw):
            if argv[:3] == ["systemctl", "--user", "restart"]:
                return subprocess.CompletedProcess(argv, 1, "", "Job failed\n")
            return orig(argv, **kw)
        r = self.start(run=refusing)
        self.assertEqual(r["status"], "failed")
        self.assertIn("restart", r["reason"])
        self.assertEqual(self.systemd.enabled, [], "nothing enabled after a failed restart")
        self.assertIs(r["stopped"], True)

    def test_a_second_start_while_one_runs_is_refused_by_the_lock_and_touches_nothing(self):
        inner = []
        self.systemd.on_enable = lambda unit: inner.append(self.start()) if not inner else None
        r = self.start()
        self.assertEqual(r["status"], "started")
        self.assertEqual(inner, [{"status": "refused", "reason": iw.LOCK_BUSY}])
        self.assertEqual(self.systemd.enabled, [DAEMON_UNIT, CLIENT_UNIT], "the refused start enabled nothing")
        self.assertEqual(len(self.systemd.rendered), 1)
        self.systemd.on_enable = None
        self.assertEqual(self.start()["status"], "started", "the lock is released: positive control")

    def test_one_lock_covers_a_start_a_stop_and_an_install(self):
        fd = os.open(os.path.join(self.state, iw.LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
        self.addCleanup(lambda: os.close(fd) if fd >= 0 else None)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        want = {"status": "refused", "reason": iw.LOCK_BUSY}
        self.assertEqual(self.start(), want)
        self.assertEqual(self.stop(), want)
        self.assertEqual(self.install(), want)
        self.nothing_touched()
        os.close(fd)
        fd = -1
        self.assertEqual(self.stop()["status"], "stopped", "positive control")

    def test_a_stop_disables_the_client_then_the_daemon_and_confirms_neither_runs(self):
        self.assertEqual(self.start()["status"], "started")
        r = self.stop()
        self.assertEqual(r, {"status": "stopped", "units": {DAEMON_UNIT: "inactive", CLIENT_UNIT: "inactive"}})
        self.assertEqual(self.systemd.disabled, [CLIENT_UNIT, DAEMON_UNIT])
        self.assertTrue(os.path.exists(self.config()), "a stop leaves the rendered config and the programs")
        self.assertEqual(self.stop()["status"], "stopped", "stopping what is stopped is stopped")

    def test_a_stop_that_leaves_a_unit_running_or_cannot_ask_is_failed_never_stopped(self):
        self.assertEqual(self.start()["status"], "started")
        self.systemd.stuck = {DAEMON_UNIT}
        r = self.stop()
        self.assertEqual(r["status"], "failed")
        self.assertIn(f"{DAEMON_UNIT} is active", r["reason"])
        self.systemd.stuck = set()
        self.systemd.disable_rc = {CLIENT_UNIT: 1}
        r = self.stop()
        self.assertEqual(r["status"], "failed", "a disable that exited non-zero")
        self.assertIn("exited 1", r["reason"])
        self.systemd.disable_rc = {}
        self.systemd.hang = "show"
        r = self.stop()
        self.assertEqual(r["status"], "failed")
        self.assertIn("did not answer", r["reason"])
        self.systemd.hang = None
        self.systemd.manager = False
        r = self.stop()
        self.assertEqual(r["status"], "failed", "no user manager: nobody confirmed anything stopped")
        self.systemd.manager = True
        self.assertEqual(self.stop()["status"], "stopped", "positive control")

    def test_without_a_roster_profile_there_is_nothing_to_start_or_stop(self):
        os.unlink(os.path.join(self.root, iw.ROSTER_REL))
        for r in (self.start(), self.stop()):
            self.assertEqual(r["status"], "failed")
            self.assertIn("roster", r["reason"])
        self.nothing_touched()

    def test_the_account_ends_with_no_scratch_and_no_unit_it_did_not_ask_for(self):
        self.start()
        self.stop()
        self.assertLessEqual(set(os.listdir(self.state)), {iw.LOCK, iw.MARKER}, "no work directory, no temporary file")


class StartStopWiring(Case):
    def test_both_are_operator_actions_with_budgets_a_table_and_a_success_set(self):
        for op in ("interweave-start", "interweave-stop"):
            self.assertIn(op, ops.OPS)
            self.assertIn(op, ACTION_OPS)
            self.assertNotIn(op, ops.PUBLIC_OPS)
        self.assertEqual(ctl.ACTION_OK["interweave-start"], ["started"])
        self.assertEqual(ctl.ACTION_OK["interweave-stop"], ["stopped"])
        a = ctl.parse_args(["db-admin", "interweave-start"])
        self.assertEqual((a["op"], a["timeout"]), ("interweave-start", iw.CARRIER_START_BUDGET_S))
        a = ctl.parse_args(["all", "interweave-stop"])
        self.assertEqual((a["op"], a["timeout"]), ("interweave-stop", iw.CARRIER_STOP_BUDGET_S))
        req = ctl.build_request(a, id="i", from_="h/user", to="*", cfg={"ttl_s": 30})
        self.assertNotIn("args", req)
        for argv in (["all", "interweave-start", "--version", "0.1.0"], ["all", "interweave-stop", "--version", "0.1.0"]):
            with self.assertRaises(ctl.CtlError, msg=argv):
                ctl.parse_args(argv)

    def test_the_budget_is_the_sum_of_what_the_action_may_wait_for(self):
        c = iw.CHECK_BUDGET_S
        sysctl, polls = iw.SYSTEMCTL_TIMEOUT_S, iw.CHECK_POLLS
        settle = polls * sysctl + (polls - 1) * iw.POLL_S
        # term by term, so a wait taken out of the budget (a restart, the cold carrier's longer status wait) is seen
        self.assertEqual(iw.CARRIER_START_BUDGET_S,
                         iw.LOGINCTL_TIMEOUT_S + 2 * iw.VERSION_TIMEOUT_S + iw.RENDER_TIMEOUT_S
                         + iw.RENDER_LEASE_WAIT_S + iw.LEASE_GRACE_S    # the queue for the render, the lease's own grace
                         + 2 * sysctl                                   # the two units' states before
                         + sysctl                                       # the restart of the one unit that ran
                         + 2 * sysctl                                   # enable --now, daemon then client
                         + c + (iw.STARTUP_STATUS_POLLS - polls) * (iw.STATUS_TIMEOUT_S + iw.POLL_S)
                         + 2 * sysctl + 2 * settle + 20)                # a failure: disable --now both, settled
        self.assertGreater(iw.CARRIER_STOP_BUDGET_S, 2 * iw.SYSTEMCTL_TIMEOUT_S)

    def test_the_daemon_answers_both_in_the_wires_reply_shape_and_a_refusal_is_one(self):
        systemd = UnitSystemd()
        t = self._tmp.name
        systemd.proc = os.path.join(t, "proc")
        systemd.bindir = os.path.join(self.home, ".local", "bin")
        self.release()
        self.assertEqual(self.install(run=systemd)["status"], "installed")
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-25T10:00:00.000Z", "home": self.home, "root": self.root,
               "carrier_unit_opts": {"state": self.state, "run": systemd, "sleep": lambda s: None}}
        r = agentd.answer({"id": "q", "op": "interweave-stop", "to": "*", "from": "h/user"}, ctx)
        self.assertEqual((r["op"], list(r["data"]), r["data"]["interweave-stop"]["status"]), ("interweave-stop", ["interweave-stop", "agentd"], "stopped"))
        r = agentd.answer({"id": "q2", "op": "interweave-start", "to": "*", "args": {"x": 1}, "from": "h/user"}, ctx)
        self.assertEqual((list(r["data"]), r["data"]["interweave-start"]["status"]), (["interweave-start", "agentd"], "refused"))

    def test_the_tables_name_each_account_and_never_an_unanswered_one_as_started(self):
        rows = [{"account": "a", "status": "ok", "interweaveStart": {"status": "started", "units": {DAEMON_UNIT: "active", CLIENT_UNIT: "active"}, "check": "passed"}},
                {"account": "b", "status": "no answer"},
                {"account": "c", "status": "ok", "interweaveStart": {"status": "refused", "reason": "c has no linger\u0007"}},
                {"account": "d", "status": "ok", "interweaveStart": {"status": "started", "already_running": True, "units": {DAEMON_UNIT: "active"}}},
                {"account": "e", "status": "ok", "interweaveStart": {"status": "started", "rerendered": True, "units": {DAEMON_UNIT: "active"}}}]
        t = ctl.table("interweave-start", rows).split("\n")
        self.assertRegex(t[1], r"^a +started +daemon active, client active")
        self.assertEqual(t[2].split()[:2], ["b", "no"])
        self.assertIn("has no linger", t[3])
        self.assertNotIn("\u0007", t[3])
        self.assertIn("already running", t[4])
        self.assertIn("re-rendered", t[5])
        self.assertNotIn("already running", t[5])
        s = ctl.table("interweave-stop", [{"account": "a", "status": "ok", "interweaveStop": {"status": "stopped", "units": {DAEMON_UNIT: "inactive"}}}]).split("\n")
        self.assertRegex(s[1], r"^a +stopped +daemon inactive")


if __name__ == "__main__":
    unittest.main()
