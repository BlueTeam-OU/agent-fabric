"""Shared plumbing of the hook contract tests (tests/test_model_fallback_note_cli.py,
test_plan_hold_cli.py, test_statusline_cli.py, test_session_start_hook_cli.py,
test_tab_title_cli.py): drive a Claude Code hook the way the harness does and
read back its exit status and streams.

    ENTRY = hook_harness.entry("PLAN_HOLD_HOOK", "plan-hold.sh")   # one constant names the entry point
    t = hook_harness.Tests("plan hold")
    r = hook_harness.run(ENTRY, payload, hook_harness.env(home))
    t.check("silent", r.rc == 0 and r.out == "", r.out)
    sys.exit(t.finish())

The entry is executed as a program (its shebang and mode bit are part of the
contract), never as `bash <file>`, so the same test runs against the shell
script today and against whatever replaces it at the same path. The
environment is built from nothing: a hook that reads a variable the test did
not give it sees it absent, as under CI, never the session's credentials,
locale or proxy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
HOOKS = os.path.join(ROOT, "runtime", "claude-code", "hooks")
TIMEOUT_S = 60


def entry(variable: str, filename: str) -> str:
    """The hook under test: $<variable> when set, else the tracked one. Exits when it is not there."""
    path = os.path.abspath(os.environ.get(variable) or os.path.join(HOOKS, filename))
    if not os.path.isfile(path):
        sys.exit(f"test: not found: {path}")
    return path


def sandbox(prefix: str) -> str:
    return tempfile.mkdtemp(prefix=prefix)


def env(home: str, **extra: str) -> dict[str, str]:
    """The minimal environment a hook runs in: PATH (the tools every hook needs), a scratch HOME, a UTF-8 locale,
    git cut off from the machine's config. Nothing else; `extra` is what a case sets on purpose."""
    base = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home,
        "LC_ALL": "C.UTF-8",
        "TMPDIR": home,
        "XDG_CACHE_HOME": os.path.join(home, ".cache"),
        "XDG_STATE_HOME": os.path.join(home, ".state"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    return {**base, **extra}


@dataclass
class Result:
    rc: int
    out: str
    err: str


def run(program: str, stdin: str, environment: dict[str, str], cwd: str | None = None) -> Result:
    p = subprocess.run([program], input=stdin.encode(), env=environment, cwd=cwd, capture_output=True, timeout=TIMEOUT_S)
    return Result(p.returncode, p.stdout.decode("utf-8", "surrogateescape"), p.stderr.decode("utf-8", "surrogateescape"))


def run_isolated(program: str, stdin: str, environment: dict[str, str], cwd: str | None = None) -> Result:
    """A module the way its forwarder runs it: `python -I <module>`, which leaves the module's own directory off
    sys.path, so a sibling import that does not find its siblings fails here and not only in the installed hook."""
    p = subprocess.run([sys.executable, "-I", program], input=stdin.encode(), env=environment, cwd=cwd, capture_output=True, timeout=TIMEOUT_S)
    return Result(p.returncode, p.stdout.decode("utf-8", "surrogateescape"), p.stderr.decode("utf-8", "surrogateescape"))


def run_in_removed_directory(program: str, stdin: str, environment: dict[str, str], parent: str) -> tuple[Result, str]:
    """The program started in a directory that was removed after it became the cwd, with $PWD still naming it: what
    a hook sees when the session deleted the directory it was launched in. Returns the result and that path."""
    gone = os.path.join(parent, "gone")
    launcher = "import os, sys; os.mkdir(sys.argv[1]); os.chdir(sys.argv[1]); os.rmdir(sys.argv[1]); os.execv(sys.argv[2], [sys.argv[2]])"
    p = subprocess.run([sys.executable, "-c", launcher, gone, program], input=stdin.encode(), env={**environment, "PWD": gone},
                       capture_output=True, timeout=TIMEOUT_S)
    return Result(p.returncode, p.stdout.decode("utf-8", "surrogateescape"), p.stderr.decode("utf-8", "surrogateescape")), gone


def tool_dir(dest: str, names: list[str]) -> str:
    """A directory holding links to exactly `names`, found on the real PATH: a PATH of it is a machine that lacks every other tool."""
    os.makedirs(dest, exist_ok=True)
    for name in names:
        found = shutil.which(name)
        if found is None:
            sys.exit(f"test: {name} is required")
        os.symlink(found, os.path.join(dest, name))
    return dest


class Tests:
    def __init__(self, title: str) -> None:
        self.title = title
        self.failures = 0

    def group(self, text: str) -> None:
        print(f"{self.title}: {text}")

    def check(self, label: str, good: bool, detail: str = "") -> None:
        if good:
            print(f"  ok   {label}")
            return
        self.failures += 1
        print(f"  FAIL {label}: {detail}" if detail else f"  FAIL {label}")

    def finish(self) -> int:
        if self.failures:
            print(f"{self.title}: {self.failures} failure(s)")
            return 1
        print(f"{self.title}: OK — all assertions passed.")
        return 0
