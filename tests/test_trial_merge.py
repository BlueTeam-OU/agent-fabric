#!/usr/bin/env python3
"""Tests for tools/fabric/github/trial_merge.py's internals; the behaviour
is tests/test_trial_merge_cli.py's, run through fabric-pr (ADR-040 §5
rule 5). What that oracle cannot reach is here: a PR number (no gh in its
fixtures), the verdict and config readings at their edges, the sweep's
liveness rule."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import trial_merge as tm  # noqa: E402


def sh(cwd: str, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@e.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True, env=env).stdout


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    scratch = tempfile.mkdtemp(prefix="test_trial_merge.")
    try:
        print("tail is the shell's: last lines, trailing newlines gone, empty stays empty")
        check("last two of four", tm.tail("a\nb\nc\nd", 2) == "c\nd")
        check("fewer lines than asked", tm.tail("a\nb", 3) == "a\nb")
        check("empty", tm.tail("", 3) == "")

        print("a verdict is read from the last matching line, and only PASS/FAIL decide")
        pat = "^trial-check: (PASS|FAIL|UNAVAILABLE)"
        check("last line wins", tm.verdict_in(pat, "trial-check: FAIL a\nnoise\ntrial-check: PASS b") == "PASS")
        check("anchored: an indented line does not match", tm.verdict_in(pat, "  trial-check: PASS") == "")
        check("no match", tm.verdict_in(pat, "make: *** Error 2") == "")
        check("not a regex", tm.verdict_in("(", "x") == "")
        check("a POSIX class, as grep -E reads it", tm.verdict_in("[[:digit:]]+ (PASS)", "x\n12 PASS") == "PASS")
        check("...and not matching", tm.verdict_in("[[:digit:]]+ (PASS)", "x PASS") == "")
        check("an empty match is nothing", tm.verdict_in("x*", "abc") == "")

        print("classify: only a pass reads as a pass")
        for rc in (124, 125, 137, 126, 127, 75):
            check(f"exit {rc} is unavailable, even with a PASS line", tm.classify(rc, pat, "trial-check: PASS") == "unavailable")
        check("no verdict declared: 0 passes", tm.classify(0, "", "") == "passed")
        check("no verdict declared: 3 fails", tm.classify(3, "", "") == "failed")
        check("verdict PASS beats exit 2", tm.classify(2, pat, "trial-check: PASS") == "passed")
        check("verdict FAIL beats exit 0", tm.classify(0, pat, "trial-check: FAIL") == "failed")
        check("verdict UNAVAILABLE", tm.classify(2, pat, "trial-check: UNAVAILABLE") == "unavailable")
        check("declared verdict absent, exit 0", tm.classify(0, pat, "done") == "unavailable")

        print("exit codes")
        for result, state, want in (("combines", "not asked", 0), ("combines", "passed", 0), ("conflicts", "not asked", 1),
                                    ("could not merge", "not asked", 2), ("combines", "failed", 1),
                                    ("combines", "unavailable", 2), ("conflicts", "not run: did not combine", 1),
                                    ("could not merge", "failed", 1)):
            check(f"{result} / {state} -> {want}", tm.exit_code(result, state) == want)

        print("the trial.json reading is jq's")
        cfg = os.path.join(scratch, "trial.json")

        def load(text):
            with open(cfg, "w") as fh:
                fh.write(text)
            return tm.load_check(cfg)

        check("full", load('{"check": ["make", "t"], "timeout_s": 600, "verdict": "^v", "lease": "l"}') == (["make", "t"], "600", "l", "^v"))
        check("defaults", load('{"check": ["a"]}') == (["a"], "1800", "", ""))
        check("null and false are unset", load('{"check": ["a"], "timeout_s": null, "lease": false}') == (["a"], "1800", "", ""))
        check("timeout text kept: 2m", load('{"check": ["a"], "timeout_s": "2m"}')[1] == "2m")
        check("timeout number: 1.5", load('{"check": ["a"], "timeout_s": 1.5}')[1] == "1.5")
        check("scalars print as jq prints them", load('{"check": ["a", 1, true, null]}')[0] == ["a", "1", "true", "null"])
        check("an argument with a newline stays one", load('{"check": ["sh", "-c", "a\\nb"]}')[0] == ["sh", "-c", "a\nb"])
        check("empty object: none", load("{}")[0] == [])
        check("check that is not a list: none", load('{"check": "make"}')[0] == [])
        check("not an object: none", load("[1]")[0] == [])
        check("missing file: none", tm.load_check(os.path.join(scratch, "absent.json"))[0] == [])
        check("empty path: none", tm.load_check("")[0] == [])
        check("not JSON: none (and said on stderr)", load("{nope")[0] == [])

        print("the reports")
        base = {"base": "origin/main", "base_sha": "a" * 40, "names": ["h/a/one", "h/b/two"], "shas": ["b" * 40, "c" * 40],
                "result": "combines", "failed_ref": "", "conflicted": [], "tree": "d" * 40, "merge_err": "",
                "check_state": "not asked", "check_rc": None, "check_tail": "", "seconds": 1}
        check("text: combines", tm.render_text(base) == "trial-merge onto origin/main (aaaaaaaa):\n  h/a/one @ bbbbbbbb\n  h/b/two @ cccccccc\n"
              "combines — tree dddddddddddd")
        j = json.loads(tm.render_json(base))
        check("json: keys in the bash's order, no check_exit", list(j) == ["base", "base_sha", "refs", "result", "tree", "check", "seconds"])
        bad = {**base, "result": "conflicts", "failed_ref": "h/b/two", "conflicted": ["f.txt"], "tree": "", "merge_err": "x\ny\nz\nw",
               "check_state": "not run: did not combine"}
        check("text: conflicts lists the paths", "conflicts — h/b/two did not merge:\n    f.txt" in tm.render_text(bad))
        check("text: check not run", tm.render_text(bad).endswith("check: not run — the refs did not combine"))
        j = json.loads(tm.render_json(bad))
        check("json: conflict keys, git is the last 3 lines", list(j)[4:7] == ["failed_ref", "conflicted", "git"] and j["git"] == "y\nz\nw")
        ran = {**base, "check_state": "failed", "check_rc": 3, "check_tail": "building\nboom"}
        check("text: a failed check shows its tail", tm.render_text(ran).endswith("check failed (exit 3)\n    building\n    boom"))
        check("json: check_exit and check_tail, then seconds", list(json.loads(tm.render_json(ran)))[-3:] == ["check_exit", "check_tail", "seconds"])
        check("text: a passed check shows no tail", tm.render_text({**ran, "check_state": "passed", "check_rc": 0}).endswith("check passed (exit 0)"))
        check("text: an empty tail prints one empty indented line", tm.render_text({**ran, "check_tail": ""}).endswith("(exit 3)\n    "))
        check("json: DEL is escaped as jq does", "\\u007f" in tm.render_json({**ran, "check_tail": "a\x7fb"}))

        print("a pid file's owner is live unless it is provably gone")
        pid_file = os.path.join(scratch, "x.pid")

        def pidf(text):
            with open(pid_file, "w") as fh:
                fh.write(text)
            return tm.pid_alive(pid_file)

        check("this process", pidf(f"{os.getpid()}\n") is True)
        check("init, owned by another login (EPERM)", pidf("1\n") is True)
        check("empty file", pidf("") is False)
        check("not a number", pidf("abc") is False)
        check("zero", pidf("0") is False)
        check("no file", tm.pid_alive(os.path.join(scratch, "none.pid")) is False)
        gone = subprocess.Popen(["true"])
        gone.wait()
        check("a reaped child", pidf(f"{gone.pid}") is False)

        print("the sweep clears a dead run's worktree and only that")
        repo, room = os.path.join(scratch, "repo"), os.path.join(scratch, "room")
        os.makedirs(room)
        sh(scratch, "init", "-q", "-b", "main", repo)
        dead, live, stale, fresh = (os.path.join(room, f"trial-merge.{n}") for n in ("DEAD", "LIVE", "STALE", "FRESH"))
        for d in (dead, live, stale, fresh):
            os.mkdir(d)
        # Linux never assigns a pid of 2**22 or more (pid_max's ceiling).
        # 999999 can be live: on a host whose pids had passed a million,
        # this case failed in a full suite run and passed alone (2026-10-09).
        for d, pid in ((dead, str(2**22 + 1)), (live, str(os.getpid()))):
            with open(d + ".pid", "w") as fh:
                fh.write(pid)
        for suffix in (".out", ".pid.tmp"):
            open(dead + suffix, "w").close()
        os.utime(stale, (time.time() - 7200,) * 2)
        tm.sweep(repo, room)
        check("dead run's dir, pid, out, tmp gone", not any(os.path.exists(dead + s) for s in ("", ".pid", ".out", ".pid.tmp")))
        check("a live owner's worktree stays", os.path.isdir(live) and os.path.exists(live + ".pid"))
        check("a pid-less worktree an hour old goes", not os.path.exists(stale))
        check("a pid-less fresh one stays", os.path.isdir(fresh))

        print("refs: a PR by its head branch, a branch by name, origin/ once")
        origin = os.path.join(scratch, "origin.git")
        sh(scratch, "init", "-q", "--bare", "-b", "main", origin)
        sh(repo, "remote", "add", "origin", origin)
        with open(os.path.join(repo, "f"), "w") as fh:
            fh.write("x\n")
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "base")
        sh(repo, "push", "-q", "origin", "main")
        sh(repo, "checkout", "-q", "-b", "h/a/feat")
        sh(repo, "commit", "-q", "--allow-empty", "-m", "feat")
        sh(repo, "push", "-q", "origin", "h/a/feat")
        sh(repo, "fetch", "-q", "origin")
        sha = sh(repo, "rev-parse", "origin/h/a/feat").strip()
        real_run, real_which = gh.run, shutil.which
        asked = []

        def fake_run(args, **kw):
            asked.append(args)
            return json.dumps({"headRefName": {"7": "h/a/feat", "0008": "origin/h/a/feat", "9": None, "10": "h/a/gone"}.get(args[2])})

        gh.run = fake_run
        try:
            check("a branch by name", tm.resolve_refs(repo, ["h/a/feat"]) == (["h/a/feat"], [sha]))
            check("origin/ stripped", tm.resolve_refs(repo, ["origin/h/a/feat"]) == (["h/a/feat"], [sha]))
            check("a PR number becomes its head branch", tm.resolve_refs(repo, ["7"]) == (["h/a/feat"], [sha]) and asked == [["pr", "view", "7", "--json", "headRefName"]])
            check("the number as typed, and a head carrying origin/", tm.resolve_refs(repo, ["0008"]) == (["h/a/feat"], [sha]) and asked[-1][2] == "0008")
            for ref, want in (("9", "is not a pull request gh can read"), ("10", "h/a/gone is not a branch on origin"),
                              ("nowhere", "nowhere is not a branch on origin"), ("", " is not a branch on origin")):
                try:
                    tm.resolve_refs(repo, [ref])
                    check(f"refused: {ref!r}", False)
                except tm.Refused as e:
                    check(f"refused: {ref!r}", want in str(e) and "nothing tried" in str(e))

            def failing(args, **kw):
                raise gh.GhError("gh pr view 7", "Not Found (HTTP 404)", 404)

            gh.run = failing
            try:
                tm.resolve_refs(repo, ["7"])
                check("a gh failure is refused", False)
            except tm.Refused as e:
                check("a gh failure is refused, naming the PR", "#7 is not a pull request gh can read" in str(e))
            shutil.which = lambda name, *a, **k: None if name == "gh" else real_which(name, *a, **k)
            try:
                tm.resolve_refs(repo, ["7"])
                check("no gh installed is refused", False)
            except tm.Refused as e:
                check("no gh installed: #7 needs gh to find its branch", "#7 needs gh to find its branch" in str(e))
            check("...but a branch name never needs gh", tm.resolve_refs(repo, ["h/a/feat"]) == (["h/a/feat"], [sha]))
        finally:
            gh.run, shutil.which = real_run, real_which

        print("merging: a failure that is not a conflict says so")
        wt = os.path.join(scratch, "wt")
        sh(repo, "checkout", "-q", "main")
        sh(repo, "worktree", "add", "-q", "--detach", wt, "main")
        sh(repo, "checkout", "-q", "--orphan", "alien")
        sh(repo, "rm", "-rfq", ".")
        open(os.path.join(repo, "a"), "w").close()
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "alien")
        alien = sh(repo, "rev-parse", "HEAD").strip()
        result, failed, conflicted, tree, err = tm.merge_all(wt, [sha, alien], ["h/a/feat", "alien"])
        check("unrelated histories: could not merge, the second ref, git's line",
              (result, failed, conflicted, tree) == ("could not merge", "alien", [], "") and "unrelated histories" in err)
        check("...and the worktree is left clean (merge aborted)", sh(wt, "status", "--porcelain") == "")
        # A post-merge hook in the clone: --no-verify does not skip it, and
        # the trial is never a merge anyone made (review of #71).
        hooks = os.path.join(scratch, "hooks")
        os.makedirs(hooks, exist_ok=True)
        marker = os.path.join(scratch, "post-merge-ran")
        with open(os.path.join(hooks, "post-merge"), "w") as f:
            f.write(f"#!/bin/sh\ntouch {marker}\n")
        os.chmod(os.path.join(hooks, "post-merge"), 0o755)
        sh(repo, "config", "core.hooksPath", hooks)
        # Back to main first: the case above merged this ref already, and an
        # "already up to date" merge runs no hook at all.
        sh(wt, "reset", "-q", "--hard", "main")
        result, _failed, _conflicted, tree, _err = tm.merge_all(wt, [sha], ["h/a/feat"])
        sh(repo, "config", "--unset", "core.hooksPath")
        check("a clean merge yields a tree", result == "combines" and len(tree) == 40)
        check("…and no hook of the clone ran, post-merge included", not os.path.exists(marker))
        sh(repo, "worktree", "remove", "--force", wt)

        print("no hook of the clone on the add, a conflict's abort, or the removal (review of #73)")
        sh(repo, "checkout", "-q", "main")
        for name in ("c1", "c2"):
            sh(repo, "checkout", "-q", "-b", name, "main")
            with open(os.path.join(repo, "clash.txt"), "w") as f:
                f.write(name + "\n")
            sh(repo, "add", "-A")
            sh(repo, "commit", "-q", "-m", name)
        sh(repo, "checkout", "-q", "main")
        c1, c2 = (sh(repo, "rev-parse", n).strip() for n in ("c1", "c2"))
        markers = {}
        for hook in ("post-checkout", "post-merge", "reference-transaction"):
            markers[hook] = os.path.join(scratch, f"{hook}-ran")
            with open(os.path.join(hooks, hook), "w") as f:
                f.write(f"#!/bin/sh\ntouch {markers[hook]}\n")
            os.chmod(os.path.join(hooks, hook), 0o755)
        sh(repo, "config", "core.hooksPath", hooks)
        try:
            wt2 = os.path.join(scratch, "wt2")
            tm.add_worktree(repo, wt2, sh(repo, "rev-parse", "main").strip())
            result, failed, _c, _t, _e = tm.merge_all(wt2, [c1, c2], ["c1", "c2"])
            tm.cleanup(repo, wt2, None)
        finally:
            sh(repo, "config", "--unset", "core.hooksPath")
        check("the second ref conflicts, and the merge is aborted", (result, failed) == ("conflicts", "c2"))
        ran = [h for h, m in markers.items() if os.path.exists(m)]
        check(f"…and not one hook of the clone ran on any of it (ran: {ran or 'none'})", ran == [])
        check("…and the trial worktree is gone", not os.path.exists(wt2))

        print("worktree_procs finds a process by its cwd and by its session")
        sleeper = subprocess.Popen(["sleep", "30"], cwd=room, start_new_session=True)
        try:
            time.sleep(0.2)
            check("by cwd under the directory", sleeper.pid in tm.worktree_procs(room, None))
            check("not by a sibling directory", sleeper.pid not in tm.worktree_procs(os.path.join(scratch, "other"), None))
            check("by session id, wherever its cwd", sleeper.pid in tm.worktree_procs(os.path.join(scratch, "other"), sleeper.pid))
            check("never this process", os.getpid() not in tm.worktree_procs(os.getcwd(), None))
        finally:
            sleeper.kill()
            sleeper.wait()

        print("the free-space arithmetic and its refusals")
        old = os.environ.get("AGENT_FABRIC_TRIAL_MIN_FREE_KB")
        try:
            os.environ["AGENT_FABRIC_TRIAL_MIN_FREE_KB"] = "0"
            check("margin 0: the tree's own size in KB", tm.need_kb_for(repo, "origin/main") == 0)
            os.environ["AGENT_FABRIC_TRIAL_MIN_FREE_KB"] = "77"
            check("margin 77", tm.need_kb_for(repo, "origin/main") == 77)
            os.environ["AGENT_FABRIC_TRIAL_MIN_FREE_KB"] = ""
            check("empty margin is the default", tm.need_kb_for(repo, "origin/main") == tm.DEFAULT_MIN_FREE_KB)
            os.environ["AGENT_FABRIC_TRIAL_MIN_FREE_KB"] = "lots"
            try:
                tm.need_kb_for(repo, "origin/main")
                check("a margin that is not a number is refused", False)
            except tm.Refused:
                check("a margin that is not a number is refused", True)
        finally:
            if old is None:
                os.environ.pop("AGENT_FABRIC_TRIAL_MIN_FREE_KB", None)
            else:
                os.environ["AGENT_FABRIC_TRIAL_MIN_FREE_KB"] = old
        check("a path that is not there has no room", tm.free_kb_of(os.path.join(scratch, "nope")) == 0)

        print("the help is the bash's header, nothing else")
        check("first and last line", tm.HELP.startswith("Do these branches combine?") and tm.HELP.endswith("(default 1 GiB)"))

        print("a reader that is gone: the run still cleans up (review of #71)")
        origin, clone, room2 = (os.path.join(scratch, n) for n in ("pipe-origin.git", "pipe-clone", "pipe-room"))
        os.makedirs(room2)
        sh(scratch, "init", "-q", "--bare", origin)
        sh(scratch, "init", "-q", "-b", "main", clone)
        sh(clone, "remote", "add", "origin", origin)
        open(os.path.join(clone, "f"), "w").write("a\n")
        sh(clone, "add", "-A")
        sh(clone, "commit", "-q", "-m", "base")
        sh(clone, "push", "-q", "origin", "main")
        sh(clone, "checkout", "-q", "-b", "h/l/feat/x")
        open(os.path.join(clone, "g"), "w").write("b\n")
        sh(clone, "add", "-A")
        sh(clone, "commit", "-q", "-m", "x")
        sh(clone, "push", "-q", "origin", "h/l/feat/x")
        r_end, w_end = os.pipe()
        os.close(r_end)
        env = {**os.environ, "TMPDIR": room2, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        shim = [os.path.join(HERE, "bin", "fabric-pr"), "trial-merge"]
        rc = subprocess.run([*shim, "h/l/feat/x"], cwd=clone, env=env, stdout=w_end,
                            stderr=subprocess.DEVNULL, timeout=120).returncode
        os.close(w_end)
        check("it ends 141, as a pipe-killed run does", rc == 141)
        check("no scratch tree or pid file left", [n for n in os.listdir(room2) if n.startswith("trial-merge.")] == [])
        check("no worktree left registered", sh(clone, "worktree", "list").count("\n") == 1)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
