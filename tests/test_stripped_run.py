#!/usr/bin/env python3
"""tests/stripped_run.py on a tree this test builds: a test that reads the
tree's live instance data fails on the stripped copy, one that reads its own
fixture passes, and both pass on the tree itself (the control). A file is
run from the copy or refused, never where it lies; the git environment of
a hook reaches neither git nor the tests; a timeout or a SIGTERM leaves no
copy and no process behind."""
from __future__ import annotations

import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import git_env  # noqa: E402
import stripped_run  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

READS_HISTORY = """import subprocess
kind = subprocess.run(["git", "cat-file", "-t", "{sha}"], capture_output=True, text=True, timeout=60)
assert kind.stdout.strip() == "commit", ("the tree's old commit is unreadable", kind.stderr)
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60).stdout.strip()
assert head, "no HEAD"
"""

READS_LIVE = """import json, os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(root, "projects", "registry.json")) as fh:
    assert "live-only" in json.load(fh)["projects"]
print("ok")
"""
READS_FIXTURE = """import json, os, sys, tempfile
open(os.path.join(tempfile.gettempdir(), "left-by-the-test"), "w").close()
assert not any(k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE", "ANTHROPIC_")) for k in os.environ), "a session variable reached the test"
assert not [k for k in os.environ if k.startswith("GIT_") and not k.startswith("GIT_CONFIG_")], [k for k in os.environ if k.startswith("GIT_")]
assert os.environ.get("GIT_CONFIG_KEY_0") == "commit.gpgsign" and os.environ.get("GIT_CONFIG_VALUE_0") == "false", "signing not pinned off"
assert os.path.isdir(".git"), "the copy is not a git repository"
with tempfile.TemporaryDirectory() as d:
    with open(os.path.join(d, "registry.json"), "w") as fh:
        json.dump({"projects": {"fixture": {}}}, fh)
print("ok")
"""
# Starts a grandchild that would outlive it, records its pid, then hangs.
HANGS = """import os, subprocess, time
p = subprocess.Popen(["sleep", "300"])
with open(os.path.join({marks!r}, "grandchild"), "w") as fh:
    fh.write(str(p.pid))
time.sleep(300)
"""


def gone(pid: int, within: float = 5) -> bool:
    """The process is dead (gone, or a zombie waiting for init) within `within` s."""
    end = time.monotonic() + within
    while time.monotonic() < end:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return True
        except FileNotFoundError:
            return True
        time.sleep(0.05)
    return False


def write(tree: str, rel: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.join(tree, rel)), exist_ok=True)
    with open(os.path.join(tree, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


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
        tree = os.path.join(private, "tree")
        marks = os.path.join(private, "marks")
        sig_tmp = os.path.join(private, "sig")
        os.makedirs(marks)
        os.makedirs(sig_tmp)
        for rel, text in (("projects/registry.json", '{"projects": {"live-only": {}}}'), ("policies/x.json", "{}"),
                          ("tests/test_reads_live.py", READS_LIVE), (".gitignore", "tests/test_ignored.py\n")):
            write(tree, rel, text)
        env = git_env.git_env()          # the test's own: never the tool's ci_env, which is under test
        for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                     ["git", "commit", "-q", "--no-verify", "-m", "t"]):
            subprocess.run(argv, cwd=tree, env=env, capture_output=True, timeout=60, check=True)
        first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, env=env, capture_output=True, text=True, timeout=60,
                               check=True).stdout.strip()
        write(tree, "tests/test_reads_history.py", READS_HISTORY.format(sha=first))
        # Untracked, not ignored: uncommitted work is what is run.
        write(tree, "tests/test_reads_fixture.py", READS_FIXTURE)
        write(tree, "tests/test_hangs.py", HANGS.format(marks=marks))
        write(tree, "tests/test_ignored.py", "print('ok')\n")

        r = subprocess.run([sys.executable, "-B", "tests/test_reads_live.py"], cwd=tree, capture_output=True, text=True, timeout=60)
        check("control: tests/test_reads_live.py passes on the tree itself", r.returncode == 0, r.stderr[-300:])

        os.environ["AGENT_FABRIC_ROOT"] = "/hostile"
        try:
            lines: list[str] = []
            code = stripped_run.run(tree, ["tests/test_reads_live.py", "tests/test_reads_fixture.py"], out=lines.append)
        finally:
            del os.environ["AGENT_FABRIC_ROOT"]
        r = subprocess.run([sys.executable, "-B", "tests/test_reads_history.py"], cwd=tree, capture_output=True, text=True, timeout=60)
        check("control: a test that reads an old commit passes on the tree itself", r.returncode == 0, r.stderr[-300:])
        history: list[str] = []
        stripped_run.run(tree, ["tests/test_reads_history.py"], out=history.append)
        check("the copy keeps the tree's history: an old commit is readable from it",
              history == ["tests/test_reads_history.py: ok"], history)
        check("a test that reads the live registry fails on the stripped copy", "tests/test_reads_live.py: FAILED (exit 1)" in lines, lines)
        check("...said with its failing line", any("AssertionError" in ln or "FileNotFoundError" in ln for ln in lines), lines)
        check("an untracked test that builds its own fixture passes, no session or git variable reaching it, signing off",
              "tests/test_reads_fixture.py: ok" in lines, lines)
        check("any failure is exit 1", code == 1, code)
        check("all passing is exit 0", stripped_run.run(tree, ["tests/test_reads_fixture.py"], out=lambda s: None) == 0)
        check("the tree itself is untouched", os.path.isfile(os.path.join(tree, "projects", "registry.json")))

        # A hook's git environment never reaches the copy's git, nor the caller's repository.
        hostile = os.path.join(private, "hostile-index")
        os.environ.update(GIT_INDEX_FILE=hostile, GIT_WORK_TREE=tree)
        try:
            code = stripped_run.run(tree, ["tests/test_reads_fixture.py"], out=lambda s: None)
        finally:
            del os.environ["GIT_INDEX_FILE"], os.environ["GIT_WORK_TREE"]
        check("a hook's GIT_INDEX_FILE and GIT_WORK_TREE reach neither git nor the tests", code == 0 and not os.path.exists(hostile), code)

        # A TMPDIR reached through a link: the copy is still where its files are found.
        os.makedirs(os.path.join(private, "real"))
        os.symlink(os.path.join(private, "real"), os.path.join(private, "link"))
        tempfile.tempdir = os.path.join(private, "link")
        try:
            lines = []
            try:
                code = stripped_run.run(tree, ["tests/test_reads_fixture.py"], out=lines.append)
            except stripped_run.NotRunnable as e:
                code = f"refused: {e}"
        finally:
            tempfile.tempdir = private
        check("a TMPDIR reached through a link: the file runs from the copy, ok", code == 0 and lines == ["tests/test_reads_fixture.py: ok"],
              (code, lines))
        os.remove(os.path.join(private, "link"))
        os.rmdir(os.path.join(private, "real"))

        # 10 s: the file has to start a grandchild and mark it first, under a loaded suite too.
        saved_timeout, stripped_run.TIMEOUT_S = stripped_run.TIMEOUT_S, 10
        try:
            lines = []
            code = stripped_run.run(tree, ["tests/test_hangs.py"], out=lines.append)
        finally:
            stripped_run.TIMEOUT_S = saved_timeout
        mark = os.path.join(marks, "grandchild")
        pid = int(open(mark).read()) if os.path.exists(mark) else -1
        check("a file past its timeout is FAILED (exit timeout), exit 1", code == 1 and "tests/test_hangs.py: FAILED (exit timeout)" in lines, lines)
        check("...and the grandchild it left running is killed with it", pid > 0 and gone(pid), pid)
        if os.path.exists(mark):
            os.remove(mark)

        # SIGTERM to the run: its copy and its tests' processes go, as on an exit.
        proc = subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "stripped_run.py"), tree, "tests/test_hangs.py"],
                                env={**os.environ, "TMPDIR": sig_tmp}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.monotonic() + 60
        while not os.path.exists(mark) and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        rc = proc.wait(timeout=60)
        pid = int(open(mark).read()) if os.path.exists(mark) else -1
        check("SIGTERM ends the run as an exit: 143, no copy left in its TMPDIR", rc == 128 + signal.SIGTERM and os.listdir(sig_tmp) == [],
              (rc, os.listdir(sig_tmp)))
        check("...and no process of its tests left running", pid > 0 and gone(pid), pid)

        err = io.StringIO()
        sys.stderr, saved = err, sys.stderr
        try:
            missing = stripped_run.main([tree, "tests/test_nope.py"])
            absolute = stripped_run.main([tree, os.path.join(HERE, "test_stripped_run.py")])
            escapes = stripped_run.main([tree, "../marks/grandchild"])
            live_abs = stripped_run.main([tree, os.path.join(tree, "tests", "test_reads_live.py")])
            ignored = stripped_run.main([tree, "tests/test_ignored.py"])
            no_args = stripped_run.main([])
            with tempfile.TemporaryDirectory() as plain:
                no_repo = stripped_run.main([plain, "x.py"])
        finally:
            sys.stderr = saved
        said = err.getvalue()
        check("a file not in the tree is exit 2, said", missing == 2 and "test_nope.py" in said, said)
        check("a file outside the tree, by absolute path, is refused: exit 2, never run where it lies",
              absolute == 2 and "test_stripped_run.py" in said, (absolute, said))
        check("...and one by a relative path out of it", escapes == 2 and "../marks/grandchild" in said, (escapes, said))
        check("a file inside the tree by absolute path runs from the copy: the live reader fails there", live_abs == 1, live_abs)
        check("a test file git ignores is not in the copy: exit 2, said, never FAILED", ignored == 2 and "not in the copy" in said, said)
        check("no arguments is exit 2", no_args == 2)
        check("a directory that is no git work tree is exit 2, said", no_repo == 2 and "not a git work tree" in said, said)

        shutil.rmtree(tree)
        if os.path.exists(mark):
            os.remove(mark)
        os.rmdir(marks)
        os.rmdir(sig_tmp)
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
