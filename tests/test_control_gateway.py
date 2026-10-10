#!/usr/bin/env python3
"""Tests for tools/fabric/control/gateway.py: the `gateway-install` action and
the `gateway` read (gateway ADR-014 rules 11, 17-19). The release is a tarball
built here whose member is a shell script that answers `--version --json`; the
download is a fake that writes it (or a real local HTTP server where the
redirect and the size bound are the subject). Nothing reaches the network and
nothing is installed outside the scratch directories."""
from __future__ import annotations

import fcntl
import hashlib
import http.server
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from control import agentd, ctl, gateway as gw, ops  # noqa: E402
from control.sign import ACTION_OPS  # noqa: E402

VERSION = "0.1.0"
MEMBER = f"agent-fabric-gateway-{VERSION}-x86_64-unknown-linux-gnu/agent-fabric-gateway"
REPORTS = {"gateway_version": VERSION, "runtime_contract": 1, "plan_schemas": [0]}
BIN = "agent-fabric-gateway"
TOKEN = "ghs_SECRETVALUE0123456789"


def rd(path: str, mode: str = "r"):
    with open(path, mode) as fh:
        return fh.read()


def wr(path: str, text: str) -> None:
    with open(path, "w") as fh:
        fh.write(text)


def script(reports: dict | None = None, extra: str = "", code: int = 0, out: str | None = None) -> bytes:
    body = json.dumps(REPORTS if reports is None else reports) if out is None else out
    return f"#!/bin/sh\n{extra}\nprintf '%s\\n' '{body}'\nexit {code}\n".encode()


def tarball(members: list[tuple[str, bytes, str]]) -> bytes:
    """(name, content, kind): kind "file" or "link" (content = the target)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "link":
                info.type, info.linkname = tarfile.SYMTYPE, content.decode()
                tf.addfile(info)
            else:
                info.size, info.mode = len(content), 0o755
                tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def pin_for(artifact: bytes, **over) -> dict:
    b = {"url": "https://api.github.com/repos/o/r/releases/assets/1", "name": f"agent-fabric-gateway-{VERSION}-x86_64-unknown-linux-gnu.tar.gz",
         "sha256": hashlib.sha256(artifact).hexdigest(), "member": MEMBER, "reports": REPORTS, **over}
    return {"version": 1, "description": "fixture", "releases": {VERSION: {"x86_64": b}}}


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="test_control_gateway.")
        self.addCleanup(self._tmp.cleanup)
        t = self._tmp.name
        self.root, self.home, self.state = (os.path.join(t, n) for n in ("root", "home", "state"))
        for d in (os.path.join(self.root, "runtime"), self.home):
            os.makedirs(d)
        self.fetched: list[tuple[str, str]] = []
        self.sentinel = os.path.join(t, "ran")

    def release(self, members=None, pin_over=None, artifact: bytes | None = None) -> bytes:
        """Writes the pin, answers the artifact the fake download delivers."""
        art = artifact if artifact is not None else tarball(members or [(MEMBER, script(extra=f"touch {self.sentinel}"), "file")])
        with open(os.path.join(self.root, "runtime", "gateway.json"), "w") as fh:
            json.dump(pin_for(art, **(pin_over or {})), fh)
        self.artifact = art
        return art

    def fetch(self, url, token, dest, *a, **k):
        self.fetched.append((url, token))
        with open(dest, "wb") as fh:
            fh.write(self.artifact)
        return len(self.artifact), hashlib.sha256(self.artifact).hexdigest()

    def install(self, version=VERSION, **kw):
        opts = dict(root=self.root, home=self.home, state=self.state, fetch=self.fetch, token=lambda name: TOKEN, machine="x86_64")
        opts.update(kw)
        return gw.gateway_install({"args": {"version": version}} if version is not None else {}, **opts)

    @property
    def target(self):
        return gw.bin_path(self.home, BIN)

    def leftovers(self) -> list[str]:
        out = []
        for d in (os.path.dirname(self.target), os.path.join(self.state, "gateway-install")):
            if os.path.isdir(d):
                out += [os.path.join(d, f) for f in os.listdir(d) if f not in (BIN,)]
        return out


class Pin(unittest.TestCase):
    def test_the_committed_pin_has_the_shape_the_action_relies_on(self):
        with open(os.path.join(HERE, "runtime", "gateway.json")) as fh:
            self.assertIsNone(gw.pin_problem(json.load(fh)))
        self.assertEqual(gw.load_pin(HERE)["version"], 1)

    def test_a_pin_that_breaks_the_shape_is_refused_one_defect_at_a_time(self):
        good = pin_for(b"x")
        self.assertIsNone(gw.pin_problem(good), "positive control")
        b = lambda d: d["releases"][VERSION]["x86_64"]  # noqa: E731
        cases = {
            "not version 1": lambda d: d.update(version=2),
            "no releases": lambda d: d.update(releases={}),
            "a release that is no version": lambda d: d["releases"].update({"latest": d["releases"].pop(VERSION)}),
            "an unknown architecture": lambda d: d["releases"][VERSION].update(armv7=b(d)),
            "an http url": lambda d: b(d).update(url="http://api.github.com/x"),
            "a name that is no tarball": lambda d: b(d).update(name="x.zip"),
            "a name with a path": lambda d: b(d).update(name="a/b.tar.gz"),
            "a short digest": lambda d: b(d).update(sha256="ab" * 31),
            "an upper-case digest": lambda d: b(d).update(sha256="AB" * 32),
            "a member with no directory": lambda d: b(d).update(member=BIN),
            "a member whose binary name is odd": lambda d: b(d).update(member="x/.hidden name"),
            "two binaries in one pin": lambda d: d["releases"][VERSION].update(aarch64={**b(d), "member": "x/other"}),
            "a member that climbs": lambda d: b(d).update(member="../agent-fabric-gateway"),
            "an absolute member": lambda d: b(d).update(member="/agent-fabric-gateway"),
            "no reports": lambda d: b(d).pop("reports"),
            "a contract that is no integer": lambda d: b(d).update(reports={"gateway_version": VERSION, "runtime_contract": "1"}),
            "reports of another version": lambda d: b(d).update(reports={"gateway_version": "9.9.9", "runtime_contract": 1}),
        }
        for label, mutate in cases.items():
            d = json.loads(json.dumps(good))
            mutate(d)
            self.assertIsNotNone(gw.pin_problem(d), label)

    def test_a_pin_that_cannot_be_read_is_one_line_never_a_default(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(gw.PinError, "cannot be read"):
                gw.load_pin(root)
            os.makedirs(os.path.join(root, "runtime"))
            wr(os.path.join(root, "runtime", "gateway.json"), "{")
            with self.assertRaisesRegex(gw.PinError, "is not JSON"):
                gw.load_pin(root)


class Refusals(Case):
    def test_the_arguments_are_a_closed_set_of_one_version(self):
        self.release()
        for args in (None, {}, {"version": VERSION, "url": "https://x"}, {"version": 1}, {"version": "0.1"}, {"version": "0.1.0\n"},
                     {"version": ["0.1.0"]}, [VERSION], {"url": "https://x"}):
            r = gw.gateway_install({"args": args}, root=self.root, home=self.home, state=self.state, fetch=self.fetch,
                                   token=lambda n: TOKEN, machine="x86_64")
            self.assertEqual(r, {"status": "refused", "reason": "gateway-install takes one argument, a version"}, args)
        self.assertEqual(self.fetched, [])
        self.assertEqual(self.install(version=VERSION)["status"], "installed", "positive control: the same call with a good argument")

    def test_a_version_the_pin_lacks_and_an_architecture_it_has_no_build_for_are_refused(self):
        self.release()
        r = self.install(version="9.9.9")
        self.assertEqual((r["status"], r["reason"]), ("refused", "version 9.9.9 is not in the reviewed pin (it has 0.1.0)"))
        r = self.install(machine="armv7l")
        self.assertEqual((r["status"], r["reason"]), ("refused", "the reviewed pin has no 0.1.0 build for armv7l"))
        self.assertEqual(self.install(machine="amd64")["status"], "installed", "amd64 is x86_64")
        self.assertEqual(self.fetched[0][1], TOKEN)

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
        self.assertFalse(os.path.exists(self.target))

    def test_a_second_install_at_once_is_refused_not_queued(self):
        self.release()
        os.makedirs(self.state, exist_ok=True)
        fd = os.open(os.path.join(self.state, gw.LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        r = self.install()
        self.assertEqual(r, {"status": "refused", "reason": "another gateway-install is running on this account"})
        self.assertEqual(self.fetched, [])


class Install(Case):
    def test_it_installs_the_pinned_binary_and_says_what_it_verified(self):
        art = self.release()
        r = self.install()
        digest = hashlib.sha256(art).hexdigest()
        with open(self.target, "rb") as fh:
            installed = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(r, {"status": "installed", "version": VERSION, "sha256": digest, "installed_sha256": installed,
                             "path": self.target, "contract": 1})
        self.assertEqual(stat.S_IMODE(os.stat(self.target).st_mode), 0o755)
        self.assertEqual(self.fetched, [("https://api.github.com/repos/o/r/releases/assets/1", TOKEN)])
        marker = gw.read_marker(self.state)
        self.assertEqual((marker["version"], marker["sha256"], marker["installed_sha256"]), (VERSION, digest, installed))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.state, gw.MARKER)).st_mode), 0o600)
        self.assertEqual(self.leftovers(), [], "no temporary file survives")
        self.assertNotIn(TOKEN, json.dumps(r) + json.dumps(marker), "the token is in neither the reply nor the marker")

    def test_the_second_call_is_current_and_downloads_nothing_until_the_file_changes(self):
        self.release()
        first = self.install()
        again = self.install()
        self.assertEqual(again["status"], "current")
        self.assertEqual({k: again[k] for k in ("version", "sha256", "installed_sha256", "path")},
                         {k: first[k] for k in ("version", "sha256", "installed_sha256", "path")})
        self.assertEqual(len(self.fetched), 1)
        with open(self.target, "ab") as fh:
            fh.write(b"# edited\n")
        self.assertEqual(self.install()["status"], "installed", "a binary that no longer has the recorded digest is replaced")
        self.assertEqual(len(self.fetched), 2)

    def test_a_digest_that_differs_installs_nothing_and_executes_nothing(self):
        self.release()
        # Another artifact is delivered than the one the pin names: its member would run (and touch the sentinel) if anything ran it.
        other = tarball([(MEMBER, script(extra=f"touch {self.sentinel}") + b"# other\n", "file")])
        self.artifact = other
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"^sha256 mismatch: the pin says [0-9a-f]{64}, the download is [0-9a-f]{64}; nothing was installed$")
        self.assertFalse(os.path.exists(self.target))
        self.assertFalse(os.path.exists(self.sentinel), "nothing was executed")
        self.assertIsNone(gw.read_marker(self.state))
        self.assertEqual(self.leftovers(), [])

    def test_only_the_pinned_member_is_read_whatever_else_the_archive_holds(self):
        self.release([("../evil", b"bad", "file"), ("/etc/evil", b"bad", "file"), (MEMBER + ".sig", b"sig", "file"),
                      (MEMBER, script(), "file")])
        self.assertEqual(self.install()["status"], "installed")
        self.assertEqual(sorted(os.listdir(os.path.dirname(self.target))), [BIN])
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.home), "evil")))

    def test_a_member_that_is_missing_or_is_a_link_is_a_failure_with_the_old_binary_left(self):
        os.makedirs(os.path.dirname(self.target))
        wr(self.target, "old\n")
        os.chmod(self.target, 0o755)
        for label, members in (("missing", [("other/file", b"x", "file")]), ("a symlink", [(MEMBER, b"/bin/sh", "link")]),
                               ("a link to another member", [("x/real", script(), "file"), (MEMBER, b"x/real", "link")])):
            self.release(members)
            r = self.install()
            self.assertEqual(r["status"], "failed", label)
            self.assertIn("pinned member could not be extracted", r["reason"], label)
            if "link" in label or "symlink" in label:
                self.assertIn("is not a regular file", r["reason"], label)
            self.assertEqual(rd(self.target), "old\n", label)
            self.assertEqual(self.leftovers(), [], label)

    def test_a_member_larger_than_the_bound_is_not_extracted(self):
        self.release()
        with unittest.mock.patch.object(gw, "MAX_MEMBER_BYTES", 10):
            r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("larger than 10 bytes", r["reason"])
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.install()["status"], "installed", "positive control: within the bound")

    def test_a_binary_that_disagrees_with_the_pin_or_cannot_report_is_not_installed(self):
        os.makedirs(os.path.dirname(self.target))
        wr(self.target, "old\n")
        os.chmod(self.target, 0o755)
        cases = {
            "another version": (script(reports={**REPORTS, "gateway_version": "0.2.0"}), "gateway_version"),
            "another contract": (script(reports={**REPORTS, "runtime_contract": 2}), "runtime_contract"),
            "plan schemas": (script(reports={**REPORTS, "plan_schemas": [0, 1]}), "plan_schemas"),
            "an exit 3": (script(code=3), "exited 3"),
            "no JSON": (script(out="hello"), "could not report"),
            "a JSON array": (script(out="[1]"), "could not report"),
        }
        for label, (content, why) in cases.items():
            self.release([(MEMBER, content, "file")])
            r = self.install()
            self.assertEqual(r["status"], "failed", label)
            self.assertIn(why, r["reason"], label)
            self.assertEqual(rd(self.target), "old\n", label)
            self.assertIsNone(gw.read_marker(self.state), label)
            self.assertEqual(self.leftovers(), [], label)

    def test_a_binary_that_never_answers_is_a_failure_within_the_bound(self):
        self.release([(MEMBER, b"#!/bin/sh\nsleep 30\n", "file")])
        real = gw.version_report
        with unittest.mock.patch.object(gw, "version_report", lambda path, run=subprocess.run, timeout_s=0.5: real(path, run, 0.5)):
            r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("did not answer --version --json", r["reason"])
        self.assertEqual(self.leftovers(), [])

    def test_a_running_gateway_keeps_the_file_it_started_from(self):
        self.release()
        os.makedirs(os.path.dirname(self.target))
        wr(self.target, "#!/bin/sh\necho old\n")
        os.chmod(self.target, 0o755)
        running = open(self.target, "rb")
        self.addCleanup(running.close)
        self.assertEqual(self.install()["status"], "installed")
        self.assertEqual(running.read(), b"#!/bin/sh\necho old\n", "the open file is the old inode, whole")
        self.assertNotEqual(os.fstat(running.fileno()).st_ino, os.stat(self.target).st_ino)

    def test_the_binary_runs_with_a_minimal_environment_never_the_sessions(self):
        seen = os.path.join(self._tmp.name, "env")
        self.release([(MEMBER, script(extra=f"env > {seen}"), "file")])
        with unittest.mock.patch.dict(os.environ, {"GH_TOKEN": TOKEN, "SOME_SECRET": "s3"}):
            self.assertEqual(self.install()["status"], "installed")
        text = rd(seen)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("SOME_SECRET", text)

    def test_directories_that_cannot_be_made_or_a_binary_that_cannot_be_read_are_replies_not_escapes(self):
        self.release()
        afile = os.path.join(self._tmp.name, "afile")
        wr(afile, "")
        r = self.install(state=os.path.join(afile, "sub"))
        self.assertEqual(r["status"], "failed")
        self.assertIn("state directory cannot be prepared", r["reason"])
        os.makedirs(os.path.join(self.home, ".local"))
        wr(os.path.join(self.home, ".local", "bin"), "")      # ~/.local/bin is a file
        r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("install directories cannot be prepared", r["reason"])
        os.unlink(os.path.join(self.home, ".local", "bin"))
        self.assertEqual(self.install()["status"], "installed", "positive control: the same install with a directory")
        if os.geteuid() != 0:
            os.chmod(self.target, 0o000)      # a binary this account cannot read is not shown to be the release
            self.assertEqual(self.install()["status"], "installed")

    def test_a_marker_that_cannot_be_written_leaves_no_temporary_file(self):
        os.makedirs(self.state)
        with unittest.mock.patch.object(gw.json, "dumps", side_effect=ValueError("bad")), self.assertRaises(ValueError):
            gw.write_marker(self.state, {"a": 1})
        self.assertEqual(os.listdir(self.state), [])

    def test_a_failure_verified_nothing_so_it_carries_no_digest(self):
        self.release()
        for r in (self.install(token=lambda n: None), self.install(fetch=lambda *a, **k: (_ for _ in ()).throw(OSError("down")))):
            self.assertEqual(r["status"], "failed")
            self.assertNotIn("sha256", r)
        self.artifact = b"other"
        self.assertNotIn("sha256", self.install(), "a digest mismatch too: the pin's digest is not a verified one")

    def test_an_http_protocol_error_or_a_late_oserror_is_a_failure_reply_never_an_escape(self):
        import http.client
        self.release()
        def short(*a, **k):
            raise http.client.IncompleteRead(b"abc", 13)
        r = self.install(fetch=short)
        self.assertEqual(r["status"], "failed")
        self.assertIn("the download failed", r["reason"])
        with unittest.mock.patch.object(gw.os, "replace", side_effect=PermissionError(13, "denied")):
            r = self.install()
        self.assertEqual((r["status"], os.path.exists(self.target)), ("failed", False))
        self.assertIn("the old one is untouched", r["reason"])
        with unittest.mock.patch.object(gw, "write_marker", side_effect=OSError(28, "full")):
            r = self.install()
        self.assertEqual(r["status"], "failed")
        self.assertIn("in place but could not be recorded", r["reason"])
        self.assertTrue(os.path.exists(self.target))
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(self.install()["status"], "installed", "the retry the reason promises: nothing recorded, so it installs again")

    def test_the_token_is_redacted_before_the_message_is_cut_and_in_its_escaped_form(self):
        secret = "ab\\cd" + "x" * 20
        long = ("p" * 150) + secret          # the token straddles the 160-character cut
        self.assertNotIn("x", gw._why(ValueError(long), secret).replace("<token>", ""))
        self.assertNotIn("\\\\", gw._why(ValueError(f"Invalid header value {secret!r}"), secret))
        self.assertEqual(gw._why(ValueError("plain words"), secret), "plain words", "positive control: nothing to redact")

    def test_a_download_that_fails_says_why_without_the_token(self):
        self.release()
        for exc, said in ((urllib.error.HTTPError("u", 404, "Not Found", {}, None), "HTTP 404"),
                          (urllib.error.URLError(f"connection refused for {TOKEN}"), "connection refused for <token>"),
                          (TimeoutError(f"slow {TOKEN}"), "slow <token>"), (ValueError("larger than 5 bytes"), "larger than 5 bytes")):
            def boom(url, token, dest, *a, _e=exc, **k):
                raise _e
            r = self.install(fetch=boom)
            self.assertEqual(r["status"], "failed")
            self.assertIn(said, r["reason"])
            self.assertNotIn(TOKEN, json.dumps(r))
            self.assertEqual(self.leftovers(), [])


class Download(unittest.TestCase):
    """download() against real local servers: the redirect and the bounds."""

    def serve(self, handler):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_the_token_goes_to_the_first_host_and_not_on_the_redirect(self):
        seen: dict[str, dict] = {}
        data = os.urandom(70000)

        class Storage(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen["storage"] = dict(self.headers)
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a): ...
        storage = self.serve(Storage)

        class Api(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen["api"] = dict(self.headers)
                self.send_response(302)
                self.send_header("Location", storage + "/blob")
                self.end_headers()

            def log_message(self, *a): ...
        api = self.serve(Api)
        # The redirect rule wants https; these servers are local plain http, so only that check is
        # lifted here (the next case holds it): the header-dropping code is the real one.
        with unittest.mock.patch.object(gw._DropAuthOnRedirect, "allow_http", True):
            with tempfile.TemporaryDirectory() as d:
                dest = os.path.join(d, "a")
                n, digest = gw.download(api + "/asset", TOKEN, dest)
                self.assertEqual((n, digest), (len(data), hashlib.sha256(data).hexdigest()))
                self.assertEqual(rd(dest, "rb"), data)
                self.assertEqual(stat.S_IMODE(os.stat(dest).st_mode), 0o600)
        self.assertEqual(seen["api"].get("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(seen["api"].get("Accept"), "application/octet-stream")
        self.assertNotIn("Authorization", seen["storage"], "positive control above: the first host did get it")

    def test_a_redirect_to_a_plain_http_address_is_refused(self):
        class Api(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:9/x")
                self.end_headers()

            def log_message(self, *a): ...
        api = self.serve(Api)
        with tempfile.TemporaryDirectory() as d, self.assertRaises(urllib.error.URLError) as cm:
            gw.download(api + "/asset", TOKEN, os.path.join(d, "a"))
        self.assertIn("non-https", str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_a_download_past_the_size_bound_or_the_deadline_stops(self):
        class Big(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(3 << 20))
                self.end_headers()
                try:
                    for _ in range(3):
                        self.wfile.write(b"x" * (1 << 20))
                except OSError:
                    pass

            def log_message(self, *a): ...
        big = self.serve(Big)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "larger than"):
                gw.download(big + "/", TOKEN, os.path.join(d, "a"), max_bytes=1 << 20)
            with self.assertRaisesRegex(TimeoutError, "did not finish"):
                gw.download(big + "/", TOKEN, os.path.join(d, "b"), deadline_s=-1)
            n, _ = gw.download(big + "/", TOKEN, os.path.join(d, "c"), max_bytes=4 << 20)
            self.assertEqual(n, 3 << 20, "positive control: the same server within the bound")


    def test_a_server_that_trickles_bytes_cannot_outrun_the_deadline(self):
        import time
        class Slow(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(5_000_000))
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass

            def log_message(self, *a): ...
        slow = self.serve(Slow)
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(TimeoutError, "did not finish"):
            gw.download(slow + "/", TOKEN, os.path.join(d, "a"), deadline_s=1, read_timeout_s=5)
        self.assertLess(time.monotonic() - started, 4, "stopped near the deadline, not when the server ended (10 s)")


    def test_a_chunked_response_trickling_its_size_line_is_stopped_at_the_deadline(self):
        import time
        class Chunked(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                try:
                    self.wfile.write(b"1;")          # a chunk-size line with an extension that never ends
                    for _ in range(150):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass

            def log_message(self, *a): ...
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(TimeoutError, "did not finish within 1 s"):
            gw.download(self.serve(Chunked) + "/", TOKEN, os.path.join(d, "a"), deadline_s=1, read_timeout_s=5)
        self.assertLess(time.monotonic() - started, 4, "the size line alone would have taken 15 s")

    def test_a_server_that_trickles_its_headers_is_stopped_at_the_deadline_too(self):
        import time
        class Headers(http.server.BaseHTTPRequestHandler):
            def handle(self):
                try:
                    self.rfile.readline()
                    for _ in range(150):
                        self.wfile.write(b"H")        # a status line that never ends
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(TimeoutError, "did not finish within 1 s"):
            gw.download(self.serve(Headers) + "/", TOKEN, os.path.join(d, "a"), deadline_s=1, read_timeout_s=5)
        self.assertLess(time.monotonic() - started, 4)


class Watchdog(unittest.TestCase):
    def test_a_connection_made_after_the_deadline_is_shut_down_at_once(self):
        class Sock:
            shut = 0

            def shutdown(self, how):
                self.shut += 1
        w = gw._Watchdog(3600)
        before, after = Sock(), Sock()
        w.track(before)
        self.assertEqual(before.shut, 0, "positive control: a connection inside the deadline is left alone")
        w._fire()
        self.assertEqual(before.shut, 1)
        w.track(after)
        self.assertEqual(after.shut, 1)
        w.stop()


class Read(Case):
    def test_absent_installed_and_unreadable(self):
        self.assertEqual(gw.gateway(home=self.home, state=self.state, root=self.root)["status"], "unreadable", "no pin, no marker: the name is unknown")
        self.release()
        self.assertEqual(gw.gateway(home=self.home, state=self.state, root=self.root), {"status": "absent", "path": self.target})
        self.install()
        r = gw.gateway(home=self.home, state=self.state, root=self.root)
        self.assertEqual((r["status"], r["version"], r["contract"], r["path"]), ("ok", VERSION, 1, self.target))
        marker = gw.read_marker(self.state)
        self.assertEqual((r["installed_sha256"], r["release_sha256"]), (marker["installed_sha256"], marker["sha256"]))
        with open(self.target, "w") as fh:   # replaced behind the marker's back: still reports, no longer vouched for
            fh.write(script(reports={**REPORTS, "gateway_version": "9.9.9"}).decode())
        r = gw.gateway(home=self.home, state=self.state, root=self.root)
        self.assertEqual((r["status"], r["version"]), ("ok", "9.9.9"))
        self.assertNotIn("release_sha256", r)
        with open(self.target, "w") as fh:
            fh.write(script(code=2).decode())
        r = gw.gateway(home=self.home, state=self.state, root=self.root)
        self.assertEqual((r["status"], r["reason"]), ("unreadable", "--version --json exited 2"))
        self.assertNotIn("version", r, "unknown stays unknown")
        os.chmod(self.target, 0o644)
        self.assertEqual(gw.gateway(home=self.home, state=self.state, root=self.root)["reason"], "not an executable file")


class Wiring(Case):
    def test_the_op_is_an_operator_action_and_the_read_an_operator_read(self):
        self.assertIn("gateway-install", ops.OPS)
        self.assertIn("gateway-install", ACTION_OPS)
        self.assertIn("gateway", ops.OPS)
        self.assertNotIn("gateway", ACTION_OPS)
        self.assertNotIn("gateway", ops.PUBLIC_OPS)
        self.assertNotIn("gateway-install", ops.PUBLIC_OPS)
        self.assertIn("gateway", agentd.BESIDE_LOOP_OPS, "the read hashes and runs a binary: it does not hold the loop")

    def test_the_daemon_answers_both_in_the_wires_reply_shape(self):
        self.release()
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-10T10:00:00.000Z", "home": self.home, "root": self.root,
               "gateway_install_opts": {"state": self.state, "fetch": self.fetch, "token": lambda n: TOKEN, "machine": "x86_64"},
               "gateway_opts": {"state": self.state}}
        r = agentd.answer({"id": "q", "op": "gateway-install", "to": "*", "args": {"version": VERSION}, "from": "h/user"}, ctx)
        self.assertEqual((r["op"], list(r["data"]), r["data"]["gateway-install"]["status"]), ("gateway-install", ["gateway-install", "agentd"], "installed"))
        r = agentd.answer({"id": "q2", "op": "gateway", "to": "*", "from": "h/user"}, ctx)
        self.assertEqual((list(r["data"]), r["data"]["gateway"]["status"], r["data"]["gateway"]["version"]), (["gateway", "agentd"], "ok", VERSION))
        r = agentd.answer({"id": "q3", "op": "gateway-install", "to": "*", "args": {"zz": 1}, "from": "h/user"}, ctx)
        self.assertEqual(r["data"]["gateway-install"]["status"], "refused")


class Operator(unittest.TestCase):
    def test_the_verb_takes_one_version_and_nothing_else(self):
        a = ctl.parse_args(["all", "gateway-install", "--version", "0.1.0"])
        self.assertEqual((a["op"], a["version"], a["targets"], a["timeout"]), ("gateway-install", "0.1.0", ["all"], gw.GATEWAY_INSTALL_BUDGET_S))
        for argv, said in ((["all", "gateway-install"], "gateway-install takes --version V"),
                           (["all", "gateway-install", "--version", "0.1"], "--version takes digits.digits.digits"),
                           (["all", "gateway", "--version", "0.1.0"], "--version takes digits.digits.digits, with upgrade and gateway-install only"),
                           (["all", "ping", "--version", "0.1.0"], "with upgrade and gateway-install only")):
            with self.assertRaises(ctl.CtlError, msg=argv) as cm:
                ctl.parse_args(argv)
            self.assertIn(said, str(cm.exception))
        self.assertEqual(ctl.parse_args(["a", "gateway"])["op"], "gateway")
        self.assertIn("gateway-install --version V", ctl.USAGE)

    def test_the_request_carries_the_version_and_nothing_else(self):
        args = ctl.parse_args(["all", "gateway-install", "--version", "0.1.0"])
        req = ctl.build_request(args, id="i", from_="h/user", to="*", cfg={"ttl_s": 30})
        self.assertEqual(req["args"], {"version": "0.1.0"})
        self.assertIn(req["op"], ACTION_OPS)

    def test_the_tables_say_each_account_and_never_a_stale_or_unanswered_one_as_installed(self):
        rows = [{"account": "a", "status": "ok", "gatewayInstall": {"status": "installed", "version": "0.1.0", "sha256": "ab" * 32},
                 "gateway": {"status": "ok", "version": "0.1.0", "contract": 1, "installed_sha256": "cd" * 32}},
                {"account": "b", "status": "no answer"},
                {"account": "c", "status": "ok", "gatewayInstall": {"status": "failed", "version": "0.1.0", "sha256": "ab" * 32,
                                                                       "reason": "sha256 mismatch: x\u0007"},
                 "gateway": {"status": "absent", "path": "/h/c/.local/bin/agent-fabric-gateway"}}]
        install = ctl.table("gateway-install", rows).split("\n")
        self.assertRegex(install[1], r"^a +installed +0\.1\.0 +abababababab")
        self.assertEqual(install[2].split()[:2], ["b", "no"])
        self.assertIn("sha256 mismatch", install[3])
        self.assertNotIn("\u0007", install[3], "an account's words reach the terminal escaped")
        read = ctl.table("gateway", rows).split("\n")
        self.assertRegex(read[1], r"^a +ok +0\.1\.0 +1 +cdcdcdcdcdcd")
        self.assertRegex(read[3], r"^c +absent +- ")
        self.assertIn("installed", ctl.ACTION_OK["gateway-install"])
        self.assertNotIn("failed", ctl.ACTION_OK["gateway-install"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
