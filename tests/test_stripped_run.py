#!/usr/bin/env python3
"""tests/stripped_run.py on a tree this test builds: a test that reads the
tree's live instance data fails on the stripped copy, one that reads its own
fixture passes, and both pass on the tree itself (the control)."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stripped_run  # noqa: E402

READS_LIVE = """import json, os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(root, "projects", "registry.json")) as fh:
    assert "live-only" in json.load(fh)["projects"]
print("ok")
"""
READS_FIXTURE = """import json, os, sys, tempfile
open(os.path.join(tempfile.gettempdir(), "left-by-the-test"), "w").close()
assert not any(k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE", "ANTHROPIC_")) or k == "GIT_DIR" for k in os.environ), "a session variable reached the test"
assert os.path.isdir(".git"), "the copy is not a git repository"
with tempfile.TemporaryDirectory() as d:
    with open(os.path.join(d, "registry.json"), "w") as fh:
        json.dump({"projects": {"fixture": {}}}, fh)
print("ok")
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    # A private temp dir for the run's copies: what is left there is this
    # run's, whatever else runs beside it.
    private = tempfile.mkdtemp(prefix="test-stripped-run.")
    saved_tmpdir = os.environ.get("TMPDIR")
    try:
        tempfile.tempdir = private
        os.environ["TMPDIR"] = private       # what a child inherits, were the tool to pass it on
        with tempfile.TemporaryDirectory() as tree:
            for rel, text in (("projects/registry.json", '{"projects": {"live-only": {}}}'), ("policies/x.json", "{}"),
                              ("tests/test_reads_live.py", READS_LIVE)):
                os.makedirs(os.path.dirname(os.path.join(tree, rel)), exist_ok=True)
                with open(os.path.join(tree, rel), "w", encoding="utf-8") as fh:
                    fh.write(text)
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "-c", "commit.gpgsign=false"]
            env = {**stripped_run.ci_env(dict(os.environ)), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
            for argv in (["git", "init", "-q"], ["git", "add", "-A"], git + ["commit", "-q", "--no-verify", "-m", "t"]):
                subprocess.run(argv, cwd=tree, env=env, capture_output=True, timeout=60, check=True)
            # Untracked, not ignored: uncommitted work is what is run.
            with open(os.path.join(tree, "tests", "test_reads_fixture.py"), "w", encoding="utf-8") as fh:
                fh.write(READS_FIXTURE)

            for f in ("tests/test_reads_live.py",):
                r = subprocess.run([sys.executable, "-B", f], cwd=tree, capture_output=True, text=True, timeout=60)
                check(f"control: {f} passes on the tree itself", r.returncode == 0, r.stderr[-300:])

            os.environ["AGENT_FABRIC_ROOT"] = "/hostile"
            try:
                lines: list[str] = []
                code = stripped_run.run(tree, ["tests/test_reads_live.py", "tests/test_reads_fixture.py"], out=lines.append)
            finally:
                del os.environ["AGENT_FABRIC_ROOT"]
            check("a test that reads the live registry fails on the stripped copy", "tests/test_reads_live.py: FAILED (exit 1)" in lines, lines)
            check("...said with its failing line", any("AssertionError" in ln or "FileNotFoundError" in ln for ln in lines), lines)
            check("an untracked test that builds its own fixture passes, with no session variable reaching it",
                  "tests/test_reads_fixture.py: ok" in lines, lines)
            check("any failure is exit 1", code == 1, code)
            check("all passing is exit 0", stripped_run.run(tree, ["tests/test_reads_fixture.py"], out=lambda s: None) == 0)
            check("the tree itself is untouched", os.path.isfile(os.path.join(tree, "projects", "registry.json")))

            err = io.StringIO()
            sys.stderr, saved = err, sys.stderr
            try:
                missing = stripped_run.main([tree, "tests/test_nope.py"])
                no_args = stripped_run.main([])
                with tempfile.TemporaryDirectory() as plain:
                    no_repo = stripped_run.main([plain, "x.py"])
            finally:
                sys.stderr = saved
            check("a file not in the tree is exit 2, said", missing == 2 and "test_nope.py" in err.getvalue(), err.getvalue())
            check("no arguments is exit 2", no_args == 2)
            check("a directory that is no git work tree is exit 2, said", no_repo == 2 and "not a git work tree" in err.getvalue())
        left = os.listdir(private)
        check("the run leaves nothing behind, a file a test left in its TMPDIR included", left == [], left)
    finally:
        tempfile.tempdir = None
        if saved_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = saved_tmpdir
        shutil.rmtree(private, ignore_errors=True)   # however the checks went, the run leaves nothing
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
