#!/usr/bin/env python3
"""tests/stripped_run.py <tree> <test file>... — run test files on a copy of
a fabric tree with its instance data removed (agent-fabric ADR-045 §5 rule
3: tests read instance fixtures, never the checkout's live instance files).

tests/test_tests_read_fixtures.py scans test SOURCE, so it cannot see a test
that reaches the live data through a tool it runs (the tool resolves the
checkout's projects/registry.json itself): seven such files went unseen
until the suite was run on a stripped copy (fabric-coordinator's request
01a11d15, its acceptance). This is that run, made repeatable.

The copy is the tree's files as git lists them, tracked and untracked but
not ignored, so uncommitted work is what is run; instance_fixtures.
strip_instance removes the instance data; the copy is made a git repository
whose HEAD is one commit of those files and whose objects hold the tree's
history, as a checkout's do (a port's test reads the old script from it).
Old commits still hold the instance data: a test that reads it through
`git show` passes here, and no test may. A test file is named by its path in the tree
(relative, or absolute inside it) and runs from the COPY: one outside the
tree, or not in the copy (an ignored file), is refused, never run where it
lies, which would read the live data and pass.

Each file runs with the caller's environment less what CI does not have
(AGENT_FABRIC_*, GITHUB_*, CLAUDE*, ANTHROPIC_*) and less every inherited
GIT_* (a hook's GIT_INDEX_FILE or GIT_WORK_TREE would aim git at the
caller's repository; tests/git_env.py), with signing pinned off as
tests/run.sh pins it; its cwd the copy, its TMPDIR a directory beside it,
in a process group of its own, under a timeout. The group is killed when
the file ends or times out, and SIGTERM or SIGHUP end the run as an exit
does, held while cleanup runs, so the copy and what the tests left are
removed however it ends. Not reached: a daemon that leaves the group by
setsid (a test's gpg-agent) outlives a run killed before the test's own
cleanup stops it; nothing short of a /proc sweep finds it, and the copy
it lived in is gone.

stdout: one line per file, "<file>: ok" or "<file>: FAILED (exit <n>)"
followed by its failing lines. A file in KNOWN_RED reads the operator's own
data on purpose (tests/test_tests_read_fixtures.py STRIPPED_RED says why):
red on a stripped copy is its answer, said as "<file>: red, deliberate — <why>"
and not counted; the same file passing is "ok". Exit 0 all passed, 1 any
failed, 2 the run could not be made or not cleaned up (no tree, not a git
work tree, a file not in it, a copy that could not be removed).
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import git_env  # noqa: E402
import instance_fixtures  # noqa: E402

TIMEOUT_S = 900
KNOWN_RED: dict[str, str] = {}
try:
    from test_tests_read_fixtures import STRIPPED_RED as KNOWN_RED  # noqa: E402,F811
except ImportError:
    pass          # a tree without the guard: every red is a failure
NOT_CI = re.compile(r"(AGENT_FABRIC_|GITHUB_|CLAUDE|ANTHROPIC_)")
# tests/run.sh's: no sandbox signs, whatever the caller's git config says.
NO_SIGNING = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
              "GIT_CONFIG_KEY_1": "tag.gpgsign", "GIT_CONFIG_VALUE_1": "false"}


class NotRunnable(Exception):
    """The run cannot be made as asked: said, exit 2."""


def ci_env(environ: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in environ.items() if not NOT_CI.match(k) and not k.startswith("GIT_")}
    return {**env, **NO_SIGNING}


def in_tree(top: str, f: str) -> str:
    """`f` as a path relative to `top`, or NotRunnable when it is not in it."""
    p = os.path.realpath(f if os.path.isabs(f) else os.path.join(top, f))
    if os.path.commonpath([p, top]) != top or not os.path.isfile(p):
        raise NotRunnable(f"not a file in {top}: {f}")
    return os.path.relpath(p, top)


def copy_tree(tree: str, dest: str) -> None:
    listed = subprocess.run(["git", "-C", tree, "ls-files", "-z", "-co", "--exclude-standard"],
                            env=git_env.git_env(ci_env(dict(os.environ))), capture_output=True, timeout=120, check=True).stdout
    for rel in (p.decode("utf-8", "surrogateescape") for p in listed.split(b"\0") if p):
        src = os.path.join(tree, rel)
        if not os.path.lexists(src):
            continue                      # listed but deleted in the work tree: not part of it
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)


def make_repo(dest: str, tree: str) -> None:
    env = git_env.git_env(ci_env(dict(os.environ)))
    subprocess.run(["git", "init", "-q"], cwd=dest, env=env, capture_output=True, timeout=120, check=True)
    # A checkout has its history; a test may read an old commit's file (the
    # oracle of a port). The tree's commits are fetched, not checked out: the
    # copy's own HEAD is one commit of the stripped files. A tree with no commit yet has none to fetch.
    has_head = subprocess.run(["git", "-C", tree, "rev-parse", "--verify", "-q", "HEAD"], env=env, capture_output=True, timeout=120)
    if has_head.returncode == 0:
        subprocess.run(["git", "fetch", "-q", "--no-tags", tree, "HEAD"], cwd=dest, env=env, capture_output=True, timeout=600, check=True)
    for argv in (["git", "add", "-A"], ["git", "commit", "-q", "--no-verify", "-m", "stripped"]):
        subprocess.run(argv, cwd=dest, env=env, capture_output=True, timeout=120, check=True)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass                              # the group is already gone


_ENDING = {signal.SIGTERM, signal.SIGHUP}


class _Held:
    """SIGTERM and SIGHUP held while cleanup runs, delivered after it: a
    second signal never cuts a kill or a removal short. Never held around
    Popen: a child inherits the blocked mask through exec."""

    def __enter__(self):
        self.old = signal.pthread_sigmask(signal.SIG_BLOCK, _ENDING)

    def __exit__(self, *exc):
        signal.pthread_sigmask(signal.SIG_SETMASK, self.old)


def run_one(argv: list[str], cwd: str, env: dict[str, str]) -> tuple[int | str, str]:
    proc = None
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", start_new_session=True)
        out, _ = proc.communicate(timeout=TIMEOUT_S)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, _ = proc.communicate()
        return "timeout", (out or "") + f"\nno answer within {TIMEOUT_S} s"
    finally:
        # A grandchild the file left running holds the copy: never past here.
        if proc is not None:
            with _Held():
                _kill_group(proc)
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()


def run(tree: str, files: list[str], out=print) -> int:
    # Resolved once: the in-copy check compares resolved paths, and a TMPDIR
    # reached through a link (macOS's /var) would refuse every file.
    base = os.path.realpath(tempfile.mkdtemp(prefix="stripped."))
    try:
        d, tmp = os.path.join(base, "tree"), os.path.join(base, "tmp")
        os.makedirs(d)
        os.makedirs(tmp)
        copy_tree(tree, d)
        instance_fixtures.strip_instance(d)
        absent = [f for f in files
                  if os.path.commonpath([os.path.realpath(os.path.join(d, f)), d]) != d or not os.path.isfile(os.path.join(d, f))]
        if absent:
            raise NotRunnable(f"not in the copy (ignored by git, or instance data): {', '.join(absent)}")
        make_repo(d, tree)
        env = {**ci_env(dict(os.environ)), "TMPDIR": tmp}
        failed = 0
        for f in files:
            code, text = run_one([sys.executable, "-B", f], d, env)
            if code == 0:
                out(f"{f}: ok")
            elif f in KNOWN_RED:
                out(f"{f}: red, deliberate — {KNOWN_RED[f]}")
            else:
                failed += 1
                out(f"{f}: FAILED (exit {code})")
                for line in [ln for ln in text.splitlines() if "FAIL" in ln or "Error" in ln][:12] or text.splitlines()[-5:]:
                    out(f"    {line}")
        return 1 if failed else 0
    finally:
        with _Held():
            shutil.rmtree(base)


def _as_exit(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: stripped_run.py <tree> <test file>...", file=sys.stderr)
        return 2
    tree = os.path.abspath(argv[0])
    try:
        top = os.path.realpath(subprocess.run(["git", "-C", tree, "rev-parse", "--show-toplevel"], capture_output=True,
                                              text=True, env=git_env.git_env(ci_env(dict(os.environ))),
                                              timeout=30, check=True).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        print(f"stripped_run: {tree} is not a git work tree", file=sys.stderr)
        return 2
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _as_exit)
    try:
        return run(top, [in_tree(top, f) for f in argv[1:]])
    except NotRunnable as e:
        print(f"stripped_run: {e}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as e:
        print(f"stripped_run: the stripped copy could not be made or removed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
