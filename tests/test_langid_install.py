#!/usr/bin/env python3
"""The oracle for runtime/langid/install.sh: the language detector's venv for
this account — made once, then left; a stale fastText model removed; a dry run
that writes nothing; a host that cannot install the package a said failure
(exit 1), not a crash. It is runtime/langid/test_install.sh, case for case,
driven through ONE constant, INSTALL (default runtime/langid/install.sh;
$LANGID_INSTALL names another entry), so the same file runs against the bash
today and against a port's shim later (ADR-040 §5 rule 5).

Nothing it runs reaches this account: HOME, the target directory
(AGENT_FABRIC_LANGID_DIR) and TMPDIR are under one mkdtemp; the package
install is the script's own override (AGENT_FABRIC_LANGID_PIP), so no network
and no compiler is used; the venv's python is a stand-in that reports
"installed" once the fake pip has run. The environment is rebuilt from PATH
and what the script reads (no AGENT_FABRIC_*, GITHUB_*, CLAUDE_* from the
session).

The bash test's cases, each a test method here:
  test_installed_once_and_the_old_model_removed   (exit 0, "+  <venv> (pycld2==…", model gone, said)
  test_second_run_is_idempotent                   ("=  <venv>")
  test_dry_run_writes_nothing                     ("would create", nothing installed)
  test_package_that_cannot_be_installed_is_said_exit_1  ("could not install", exit 1)

Added where a refactor could break the contract and the bash test is silent:
  test_dry_run_names_the_stale_model_and_keeps_it, test_dry_run_exit_status_zero,
  test_pip_command_gets_the_package_as_its_last_argument,
  test_pip_that_succeeds_but_leaves_no_pycld2_is_said_exit_1,
  test_venv_creation_failure_is_said_exit_1, test_target_directory_is_private,
  test_present_venv_with_pycld2_makes_no_pip_call, test_no_traceback_on_any_failure.

Mutations this fails on (planted on the source as formatted, 2026-10-12; all killed):
  - the old model left on disk: test_installed_once_...
  - a dry run that creates the directory: test_dry_run_writes_nothing
  - the pip status not checked (success claimed): test_package_that_cannot_...
  - the import check after the install dropped: test_pip_that_succeeds_but_...
  - rc forced to 0: the two exit-1 tests
  - the idempotence check dropped (pip rerun): test_present_venv_with_pycld2_makes_no_pip_call

Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

INSTALL = os.path.abspath(os.environ.get("LANGID_INSTALL") or os.path.join(HERE, "runtime", "langid", "install.sh"))
if not os.path.isfile(INSTALL):
    sys.exit(f"test: script under test not found at {INSTALL}")
with open(os.path.join(HERE, "runtime", "langid", "detector.json"), encoding="utf-8") as _fh:
    PACKAGE = json.load(_fh)["package"]
TIMEOUT_S = 60


class Langid(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = os.path.realpath(tempfile.mkdtemp(prefix="li."))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.home = os.path.join(self.sandbox, "home")
        os.makedirs(self.home)
        self.dir = os.path.join(self.sandbox, "langid")
        self.model = os.path.join(self.dir, "lid.176.ftz")
        self.installed = os.path.join(self.dir, "venv", "installed")
        self.pip = os.path.join(self.sandbox, "fakepip")
        self.pip_log = os.path.join(self.sandbox, "pip.log")
        self.script(self.pip, f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.pip_log}"\ntouch "{self.installed}"\n')
        self.path = os.environ.get("PATH", "/usr/bin:/bin")

    def script(self, path: str, body: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(path, 0o755)
        return path

    def fakevenv(self) -> None:
        """install.sh runs <venv>/bin/python -c "import pycld2" to decide; the stand-in exits 0 once "installed"."""
        os.makedirs(os.path.join(self.dir, "venv", "bin"), exist_ok=True)
        self.script(os.path.join(self.dir, "venv", "bin", "python"), f'#!/bin/sh\n[ -f "{self.installed}" ]\n')

    def run_install(self, *args: str, pip: str | None = None, path: str | None = None) -> subprocess.CompletedProcess:
        env = {"PATH": path or self.path, "HOME": self.home, "LANG": "C.UTF-8", "TMPDIR": self.sandbox,
               "AGENT_FABRIC_LANGID_DIR": self.dir, "AGENT_FABRIC_LANGID_PIP": self.pip if pip is None else pip}
        return subprocess.run(["bash", INSTALL, *args], capture_output=True, text=True, env=env, cwd=self.sandbox,
                              timeout=TIMEOUT_S, check=False)

    def out(self, *args: str, **kw: str) -> str:
        p = self.run_install(*args, **kw)
        return p.stdout + p.stderr

    def test_installed_once_and_the_old_model_removed(self) -> None:
        self.fakevenv()
        with open(self.model, "w", encoding="utf-8") as fh:
            fh.write("old model")
        p = self.run_install()
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        self.assertIn(f"+  {self.dir}/venv (pycld2==", out)
        self.assertFalse(os.path.exists(self.model))
        self.assertIn("removed: the detector is CLD2 now", out)

    def test_second_run_is_idempotent(self) -> None:
        self.fakevenv()
        self.run_install()
        self.assertIn(f"=  {self.dir}/venv", self.out())

    def test_dry_run_writes_nothing(self) -> None:
        os.makedirs(self.sandbox, exist_ok=True)
        self.fakevenv()
        out = self.out("--dry-run")
        self.assertIn("would create", out)
        self.assertFalse(os.path.exists(self.installed))

    def test_package_that_cannot_be_installed_is_said_exit_1(self) -> None:
        p = self.run_install(pip="/bin/false")
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 1, out)
        self.assertIn("could not install", out)

    def test_dry_run_names_the_stale_model_and_keeps_it(self) -> None:
        self.fakevenv()
        with open(self.model, "w", encoding="utf-8") as fh:
            fh.write("old model")
        out = self.out("--dry-run")
        self.assertIn(f"-  {self.model} (would remove: the detector is CLD2 now)", out)
        self.assertTrue(os.path.exists(self.model))

    def test_dry_run_exit_status_zero(self) -> None:
        self.fakevenv()
        p = self.run_install("--dry-run")
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertEqual(p.stdout.rstrip("\n"), f"  +  {self.dir}/venv (would create and install {PACKAGE})")

    def test_pip_command_gets_the_package_as_its_last_argument(self) -> None:
        # The override is split on whitespace, as the script's `read -ra`
        # does; the package is appended, never interpolated into a string.
        self.fakevenv()
        self.run_install(pip=f"{self.pip} --flag value")
        with open(self.pip_log, encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), f"--flag value {PACKAGE}")

    def test_pip_that_succeeds_but_leaves_no_pycld2_is_said_exit_1(self) -> None:
        # Positive control: the same run with the fake that does install is exit 0 (above).
        self.fakevenv()
        noop = self.script(os.path.join(self.sandbox, "noop"), "#!/bin/sh\nexit 0\n")
        p = self.run_install(pip=noop)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("could not install", p.stdout + p.stderr)

    def test_venv_creation_failure_is_said_exit_1(self) -> None:
        # A python3 first on PATH that fails `-m venv` and delegates the rest
        # (the script also reads detector.json with python3).
        fakebin = os.path.join(self.sandbox, "fakebin")
        os.makedirs(fakebin)
        real = shutil.which("python3")
        self.script(os.path.join(fakebin, "python3"),
                    f'#!/bin/sh\n[ "$1 $2" = "-m venv" ] && exit 1\nexec "{real}" "$@"\n')
        p = self.run_install(path=f"{fakebin}{os.pathsep}{self.path}")
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 1, out)
        self.assertIn("python3 -m venv failed; the language section stays unavailable", out)
        self.assertFalse(os.path.exists(self.installed))

    def test_target_directory_is_private(self) -> None:
        self.fakevenv()
        os.chmod(self.dir, 0o755)
        self.run_install()
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)

    def test_present_venv_with_pycld2_makes_no_pip_call(self) -> None:
        self.fakevenv()
        open(self.installed, "w").close()
        p = self.run_install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"=  {self.dir}/venv ({PACKAGE})", p.stdout)
        self.assertFalse(os.path.exists(self.pip_log))

    def test_no_traceback_on_any_failure(self) -> None:
        for kw in ({"pip": "/bin/false"}, {"pip": os.path.join(self.sandbox, "absent-pip")}):
            with self.subTest(**kw):
                p = self.run_install(**kw)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertNotIn("Traceback", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
