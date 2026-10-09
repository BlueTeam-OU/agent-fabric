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
strip_instance removes the instance data; the copy is made a one-commit git
repository, as a checkout is. Each file runs with the caller's environment
less what CI does not have (AGENT_FABRIC_*, GITHUB_*, CLAUDE*, ANTHROPIC_*,
GIT_DIR), its cwd the copy, its TMPDIR a directory beside the copy (what
a test leaves there is not the caller's), under a timeout. Both are
removed however the run ends.

stdout: one line per file, "<file>: ok" or "<file>: FAILED (exit <n>)"
followed by its failing lines. Exit 0 all passed, 1 any failed, 2 the run
could not be made (no tree, not a git work tree, a file not in it).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import instance_fixtures  # noqa: E402

TIMEOUT_S = 900
NOT_CI = re.compile(r"(AGENT_FABRIC_|GITHUB_|CLAUDE|ANTHROPIC_)")


def ci_env(environ: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in environ.items() if not NOT_CI.match(k) and k != "GIT_DIR"}


def copy_tree(tree: str, dest: str) -> None:
    listed = subprocess.run(["git", "-C", tree, "ls-files", "-z", "-co", "--exclude-standard"],
                            capture_output=True, timeout=120, check=True).stdout
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


def make_repo(dest: str) -> None:
    env = {**ci_env(dict(os.environ)), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                 ["git", "-c", "user.name=stripped", "-c", "user.email=stripped@invalid", "-c", "commit.gpgsign=false",
                  "commit", "-q", "--no-verify", "-m", "stripped"]):
        subprocess.run(argv, cwd=dest, env=env, capture_output=True, timeout=120, check=True)


def run(tree: str, files: list[str], out=print) -> int:
    with tempfile.TemporaryDirectory(prefix="stripped.") as base:
        d, tmp = os.path.join(base, "tree"), os.path.join(base, "tmp")
        os.makedirs(d)
        os.makedirs(tmp)
        env = {**ci_env(dict(os.environ)), "TMPDIR": tmp}
        copy_tree(tree, d)
        instance_fixtures.strip_instance(d)
        make_repo(d)
        failed = 0
        for f in files:
            try:
                r = subprocess.run([sys.executable, "-B", f], cwd=d, env=env,
                                   capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
                code, text = r.returncode, r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                code, text = "timeout", f"no answer within {TIMEOUT_S} s"
            if code == 0:
                out(f"{f}: ok")
            else:
                failed += 1
                out(f"{f}: FAILED (exit {code})")
                for line in [ln for ln in text.splitlines() if "FAIL" in ln or "Error" in ln][:12] or text.splitlines()[-5:]:
                    out(f"    {line}")
        return 1 if failed else 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: stripped_run.py <tree> <test file>...", file=sys.stderr)
        return 2
    tree, files = os.path.abspath(argv[0]), argv[1:]
    try:
        top = subprocess.run(["git", "-C", tree, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=30, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        print(f"stripped_run: {tree} is not a git work tree", file=sys.stderr)
        return 2
    missing = [f for f in files if not os.path.isfile(os.path.join(top, f))]
    if missing:
        print(f"stripped_run: not in {top}: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        return run(top, files)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"stripped_run: the stripped copy could not be made: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
