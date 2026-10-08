#!/usr/bin/env python3
"""runtime/claude-code/hooks/freshness.py against a real scratch origin and
clone: a stale fetch is started in the background and never waited on; a
checkout behind origin's default branch is said once per change; nothing is
said for a current copy, a copy with no origin, or no git at all."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "freshness.py")
spec = importlib.util.spec_from_file_location("freshness", HOOK)
fresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fresh)

ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_", "AGENT_FABRIC_"))}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
os.environ.clear()
os.environ.update(ENV)


def sh(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=60).stdout


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_freshness.") as tmp:
        origin, wc, other, state = (os.path.join(tmp, n) for n in ("origin.git", "wc", "other", "state"))
        sh("init", "-q", "--bare", "-b", "main", origin)
        sh("clone", "-q", origin, other)
        sh("commit", "-q", "--allow-empty", "-m", "one", cwd=other)
        sh("push", "-q", "origin", "main", cwd=other)
        sh("clone", "-q", origin, wc)
        p = {"cwd": wc, "session_id": "s1"}
        # A fresh clone has fetched just now: FETCH_HEAD stands for that, so
        # no background fetch starts in the cases that do not test one.
        open(os.path.join(wc, ".git", "FETCH_HEAD"), "a").close()

        check("a current copy: nothing said", fresh.note(p, state=state) is None)
        sh("commit", "-q", "--allow-empty", "-m", "two", cwd=other)
        sh("commit", "-q", "--allow-empty", "-m", "three", cwd=other)
        sh("push", "-q", "origin", "main", cwd=other)
        sh("fetch", "-q", "origin", cwd=wc)
        line = fresh.note(p, state=state)
        check("behind origin/main: one line, with the count and the remote ref to read",
              line is not None and "lacks 2 commit(s) of origin/main" in line and "git show origin/main:" in line, line)
        check("…said once: the same gap is not said again", fresh.note(p, state=state) is None)
        check("…another session is told too", fresh.note({**p, "session_id": "s2"}, state=state) is not None)
        sh("merge", "-q", "--ff-only", "origin/main", cwd=wc)
        check("caught up: nothing said", fresh.note(p, state=state) is None)
        check("…and a session current again keeps no note", not os.path.exists(os.path.join(state, "freshness-s1.json")))

        # A stale fetch is started in the background: the call returns at
        # once, and the remote ref moves on its own.
        sh("commit", "-q", "--allow-empty", "-m", "four", cwd=other)
        sh("push", "-q", "origin", "main", cwd=other)
        old = time.time() - 3600
        os.utime(os.path.join(wc, ".git", "FETCH_HEAD"), (old, old))
        t0 = time.time()
        first = fresh.note(p, state=state)
        check("a stale fetch never holds the prompt", time.time() - t0 < 3, time.time() - t0)
        head = sh("rev-parse", "main", cwd=other).strip()
        for _ in range(100):
            if sh("rev-parse", "origin/main", cwd=wc).strip() == head:
                break
            time.sleep(0.1)
        check("…and the background fetch brought origin/main up", sh("rev-parse", "origin/main", cwd=wc).strip() == head)
        # The fetch is detached: on a local remote it can land before the
        # same prompt counts, and then that prompt says the gap. Either
        # way it is said once, never twice and never not at all.
        said = [x for x in (first, fresh.note(p, state=state)) if x is not None]
        check("…so the new gap is said, exactly once", len(said) == 1 and "lacks 1 commit(s)" in said[0], said)

        # A linked worktree fetches into its own FETCH_HEAD: the throttle
        # reads that one, so a fresh worktree fetch starts no second fetch.
        wt = os.path.join(tmp, "wt")
        sh("worktree", "add", "-q", wt, "-b", "side", cwd=wc)
        sh("fetch", "-q", "origin", cwd=wt)
        old = time.time() - 3600
        os.utime(os.path.join(wc, ".git", "FETCH_HEAD"), (old, old))
        started = []
        real = fresh.fetch_detached
        fresh.fetch_detached = started.append
        try:
            fresh.note({"cwd": wt, "session_id": "s3"}, state=state)
        finally:
            fresh.fetch_detached = real
        check("a worktree's own fresh fetch: no fetch started", started == [], started)

        # No origin/HEAD and a default branch named master: the first
        # existing of main and master is read, never a missing origin/main.
        morigin, mclone, mother = (os.path.join(tmp, n) for n in ("m.git", "mwc", "mother"))
        sh("init", "-q", "--bare", "-b", "master", morigin)
        sh("init", "-q", "-b", "master", mother)
        sh("commit", "-q", "--allow-empty", "-m", "a", cwd=mother)
        sh("remote", "add", "origin", morigin, cwd=mother)
        sh("push", "-q", "origin", "master", cwd=mother)
        sh("init", "-q", "-b", "master", mclone)
        sh("remote", "add", "origin", morigin, cwd=mclone)
        sh("fetch", "-q", "origin", cwd=mclone)
        sh("reset", "-q", "--hard", "origin/master", cwd=mclone)
        sh("commit", "-q", "--allow-empty", "-m", "b", cwd=mother)
        sh("push", "-q", "origin", "master", cwd=mother)
        sh("fetch", "-q", "origin", cwd=mclone)
        line = fresh.note({"cwd": mclone, "session_id": "s4"}, state=state)
        check("no origin/HEAD, default master: the gap is said against origin/master",
              line is not None and "lacks 1 commit(s) of origin/master" in line, line)

        nogit = os.path.join(tmp, "plain")
        os.makedirs(nogit)
        check("no git working copy: nothing", fresh.note({"cwd": nogit, "session_id": "s1"}, state=state) is None)
        lone = os.path.join(tmp, "lone")
        sh("init", "-q", lone)
        check("no origin: nothing", fresh.note({"cwd": lone, "session_id": "s1"}, state=state) is None)
        check("a session id that is not a name: nothing",
              fresh.note({"cwd": wc, "session_id": "../x"}, state=state) is None)
        r = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True, timeout=30)
        check("a payload that is not JSON: exit 0, nothing printed", r.returncode == 0 and not r.stdout and not r.stderr)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
