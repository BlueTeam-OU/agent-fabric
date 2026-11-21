#!/usr/bin/env python3
"""policies/githooks/pre-push: a forwarder. git runs a file by path, so the hook stays a file; the decision (who may push what where) is
tools/fabric/githooks_prepush.py's, pinned by tests/test_githooks_prepush.py through the real hook against a real remote (Wave 9 batch 4;
ADR-040 rule 5). What the forwarder itself owes, and nothing else tests, is this file's subject; the module is a recording stand-in here, in
a scratch fabric root that holds a COPY of the hook, so each case chooses what the module answers. The seam is ONE constant, githook_fixtures.GITHOOKS_DIR
(the directory under test, default policies/githooks; the GITHOOKS_DIR environment variable overrides it; the hook is its pre-push file), run as git runs it: by path, from the repository, with the remote's name and
URL as arguments and the ref lines on stdin.

The contract the forwarder keeps (each is a method): the arguments reach the module verbatim, spaces, an empty argument and non-ASCII
included; stdin reaches it whole; its exit status is the hook's exit status; its stdout and stderr come out unchanged and apart; it runs in
the repository's directory with the caller's environment; it is found from the hook's REAL path, so a symlink to the hook (how a checkout
may install it) works; the interpreter is the fleet's pin, `${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}`, never `python3` from PATH
(ADR-040 rule 1, A 2026-11-11: every host has the pin); with the module missing the failure is the interpreter's (exit 2, the path named);
with the pin absent the push is refused, exit 127, naming the pin's path and its install command, the module never run.

Mutations each case fails on (planted on the hook as formatted): `"$@"` to `$@` (arguments); `exec "$py" ... "$@"` to `"$py" ... "$@"; exit 0`
(exit status); dropping `readlink -f` from the root (the symlinked hook); `"$py"` to `python3` (the pin, not PATH); dropping the `-x` check
(the refusal's words); `exit 127` to `exit 0` (a missing pin passes the push)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import GITHOOKS_DIR, GIT_ENV, Repo  # noqa: E402

STUB = '''#!/usr/bin/env python3
import json, os, sys
rec = {"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(), "env_marker": os.environ.get("PREPUSH_TEST_MARKER"), "exe": sys.argv[0], "py": sys.executable}
json.dump(rec, open(os.environ["PREPUSH_TEST_RECORD"], "w"))
mode = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mode.json")))
sys.stdout.write(mode.get("out", ""))
sys.stderr.write(mode.get("err", ""))
sys.exit(mode.get("exit", 0))
'''


class PrePush(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="prepush-forwarder-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.fabric = os.path.join(self.root, "fabric")
        self.hooks = os.path.join(self.fabric, "policies", "githooks")
        shutil.copytree(GITHOOKS_DIR, self.hooks, symlinks=True)
        os.makedirs(os.path.join(self.fabric, "tools", "fabric"))
        self.module = os.path.join(self.fabric, "tools", "fabric", "githooks_prepush.py")
        with open(self.module, "w", encoding="utf-8") as fh:
            fh.write(STUB)
        self.record = os.path.join(self.root, "record.json")
        self.repo = Repo({"README": "r\n"}, name="work")
        self.addCleanup(self.repo.cleanup)
        self.mode()

    def mode(self, **doc) -> None:
        with open(os.path.join(self.fabric, "tools", "fabric", "mode.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def run_hook(self, *args, stdin="", hook=None, path="/usr/bin:/bin", cwd=None, py=sys.executable):
        # The pin is this interpreter unless a case says otherwise (None: unset, the hook's own default).
        env = {**GIT_ENV, "PATH": path, "HOME": self.root, "PREPUSH_TEST_RECORD": self.record, "PREPUSH_TEST_MARKER": "marker-value"}
        if py is not None:
            env["AGENT_FABRIC_PYTHON"] = py
        return subprocess.run([hook or os.path.join(self.hooks, "pre-push"), *args], cwd=cwd or self.repo.path, input=stdin, capture_output=True,
                              text=True, timeout=60, env=env)

    def recorded(self) -> dict:
        with open(self.record, encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_arguments_reach_the_module_verbatim(self):
        args = ("origin", "git@example.invalid:org/repo with space.git", "", "ünï", "-x", "$HOME", "a;b")
        r = self.run_hook(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.recorded()["argv"], list(args))

    def test_no_arguments_are_none(self):
        self.run_hook()
        self.assertEqual(self.recorded()["argv"], [])

    def test_stdin_reaches_the_module_whole(self):
        refs = "refs/heads/main abc123 refs/heads/main def456\nrefs/heads/x 0000 refs/heads/x 1111\n"
        self.run_hook("origin", "url", stdin=refs)
        self.assertEqual(self.recorded()["stdin"], refs)

    def test_the_modules_exit_status_is_the_hooks(self):
        for code in (0, 1, 2, 3, 7, 42):
            with self.subTest(code=code):
                self.mode(exit=code)
                self.assertEqual(self.run_hook("origin", "url").returncode, code)

    def test_stdout_and_stderr_come_out_unchanged_and_apart(self):
        self.mode(out="said on stdout\n", err="said on stderr\n", exit=1)
        r = self.run_hook("origin", "url")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (1, "said on stdout\n", "said on stderr\n"))

    def test_it_runs_in_the_repository_with_the_callers_environment(self):
        self.run_hook("origin", "url")
        rec = self.recorded()
        self.assertEqual(os.path.realpath(rec["cwd"]), os.path.realpath(self.repo.path))
        self.assertEqual(rec["env_marker"], "marker-value")

    def test_the_module_is_found_from_the_hooks_real_path_so_a_symlink_to_the_hook_works(self):
        link_dir = os.path.join(self.repo.path, ".git", "hooks")
        os.makedirs(link_dir, exist_ok=True)
        link = os.path.join(link_dir, "pre-push")
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(os.path.join(self.hooks, "pre-push"), link)
        self.mode(exit=5)
        r = self.run_hook("origin", "url", hook=link)
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertEqual(self.recorded()["argv"], ["origin", "url"])

    def shim(self, name: str) -> tuple[str, str]:
        """An executable that records it ran, then runs this interpreter; (its path, its marker)."""
        shim_dir = os.path.join(self.root, "shim")
        os.makedirs(shim_dir, exist_ok=True)
        shim, marker = os.path.join(shim_dir, name), os.path.join(self.root, f"{name}-ran")
        with open(shim, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\necho ran > "{marker}"\nexec "{sys.executable}" "$@"\n')
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR)
        return shim, marker

    def test_the_interpreter_is_the_pin_named_by_agent_fabric_python(self):
        pin, pin_ran = self.shim("fabric-python")
        _, path_ran = self.shim("python3")
        r = self.run_hook("origin", "url", path=f"{os.path.dirname(pin)}:/usr/bin:/bin", py=pin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(pin_ran), "the pin was not the interpreter")
        self.assertFalse(os.path.exists(path_ran), "the python3 first on PATH ran")

    def test_unset_the_pin_is_usr_local_bin_fabric_python_never_python3_from_path(self):
        shim, path_ran = self.shim("python3")
        r = self.run_hook("origin", "url", path=f"{os.path.dirname(shim)}:/usr/bin:/bin", py=None)
        self.assertFalse(os.path.exists(path_ran), "the python3 first on PATH ran")
        if os.access("/usr/local/bin/fabric-python", os.X_OK):
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.path.realpath(self.recorded()["py"]), os.path.realpath("/usr/local/bin/fabric-python"))
        else:
            self.assertEqual(r.returncode, 127)
            self.assertIn("/usr/local/bin/fabric-python", r.stderr)

    def test_with_the_module_missing_the_failure_is_the_interpreters_and_names_the_path(self):
        os.remove(self.module)
        r = self.run_hook("origin", "url")
        self.assertEqual(r.returncode, 2)
        self.assertIn("githooks_prepush.py", r.stderr)

    def test_with_the_pin_absent_the_push_is_refused_naming_it_and_its_install(self):
        missing = os.path.join(self.root, "no-such", "fabric-python")
        r = self.run_hook("origin", "url", py=missing)
        self.assertEqual(r.returncode, 127)
        self.assertIn(f"not installed at {missing}", r.stderr)
        self.assertIn("python_pin.py install", r.stderr)
        self.assertFalse(os.path.exists(self.record), "the module ran without the pin")


if __name__ == "__main__":
    unittest.main()
