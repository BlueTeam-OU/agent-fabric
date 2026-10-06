#!/usr/bin/env python3
"""Tests for tools/fabric/branches.py's internals; the behaviour is
tests/test_fabric_branches_cli.py's, run against the shim (ADR-040 §5 rule 5).
What that oracle cannot reach is here: a git call that fails must never read
as "merged" and never delete, a branch named like an option, the current
branch and a detached HEAD, a pull request's JSON, the worktree listing's
edges."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import branches as br  # noqa: E402
import gh  # noqa: E402

SHIM = os.path.join(HERE, "bin", "fabric-branches")
GIT = shutil.which("git") or "/usr/bin/git"


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GH_TOKEN="")
    env.update(extra)
    return env


def sh(cwd: str, *args: str, env: dict | None = None) -> str:
    return subprocess.run([GIT, "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@e.invalid",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                          env=env or clean_env()).stdout


def branches_of(repo: str) -> list[str]:
    return sh(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print(f"       {detail}")
        fails += not good

    scratch = tempfile.mkdtemp(prefix="test_branches.")
    try:
        state = os.path.join(scratch, "state")
        bindir = os.path.join(scratch, "bin")
        os.makedirs(bindir)

        def tool(name: str, body: str) -> None:
            path = os.path.join(bindir, name)
            with open(path, "w") as fh:
                fh.write("#!/bin/sh\n" + body)
            os.chmod(path, 0o755)

        def fixture(name: str) -> str:
            """A clone with main, `merged` (on main), `owed` (one commit off
            it) and, on origin, nothing else."""
            origin = os.path.join(scratch, name + ".git")
            wc = os.path.join(scratch, name)
            sh(scratch, "init", "-q", "--bare", "-b", "main", origin)
            sh(scratch, "clone", "-q", origin, wc)
            sh(wc, "commit", "-q", "--allow-empty", "-m", "base")
            sh(wc, "push", "-q", "origin", "HEAD:main")
            sh(wc, "branch", "merged")
            sh(wc, "checkout", "-q", "-b", "owed")
            sh(wc, "commit", "-q", "--allow-empty", "-m", "owed")
            sh(wc, "checkout", "-q", "main")
            sh(wc, "fetch", "-q", "origin")
            return wc

        def fabric(wc: str, *args: str, path_first: str | None = None, env: dict | None = None):
            e = env or clean_env(AGENT_FABRIC_STATE_DIR=state)
            if path_first:
                e = {**e, "PATH": path_first + os.pathsep + e["PATH"]}
            return subprocess.run(["bash", SHIM, *args], cwd=wc, capture_output=True, text=True, env=e, timeout=120)

        tool("gh", "exit 1\n")

        print("a count is a number or `?`, and `?` is never 0")
        wc = fixture("counts")
        cwd = os.getcwd()
        os.chdir(wc)
        try:
            check("a merged branch is 0", br.ahead("merged", "origin/main") == "0")
            check("a branch with a commit off main is 1", br.ahead("owed", "origin/main") == "1")
            check("a ref git does not know is ?", br.ahead("nope", "origin/main") == "?")
            check("an empty ref counts HEAD, as the bash did", br.ahead("", "origin/main") == "0")
        finally:
            os.chdir(cwd)

        print("the worktree listing")
        sh(wc, "worktree", "add", "-q", os.path.join(scratch, "wt-a"), "-b", "wt-a", "main")
        sh(wc, "worktree", "add", "-q", "--detach", os.path.join(scratch, "wt b"), "main")
        sh(wc, "worktree", "lock", os.path.join(scratch, "wt-a"))
        os.chdir(wc)
        try:
            found = br.worktrees()
        finally:
            os.chdir(cwd)
        by_path = {os.path.basename(w["path"]): w for w in found}
        check("the main one is first", os.path.basename(found[0]["path"]) == "counts")
        check("a branch is its short name", by_path["wt-a"]["branch"] == "wt-a")
        check("a locked one is locked", by_path["wt-a"]["locked"] is True and by_path["counts"]["locked"] is False)
        check("a detached one has no branch and a head", by_path["wt b"]["branch"] == "" and len(by_path["wt b"]["head"]) == 40)
        check("a path with a space is whole", by_path["wt b"]["path"].endswith("wt b"))

        print("a pull request is read as JSON and said as the bash said it")
        real = gh.run

        def fake(out):
            def run(args, **kw):
                if isinstance(out, Exception):
                    raise out
                return out
            return run
        try:
            for label, answer, want in (
                    ("none", "[]", ""),
                    ("two", '[{"number":7,"state":"OPEN"},{"number":9,"state":"MERGED"}]', "#7 OPEN, #9 MERGED"),
                    ("gh failed", gh.GhError("gh pr list", "no"), "?"),
                    ("not JSON", "garbage", "?"),
                    ("not a list", '{"number":1}', "?"),
                    ("a row that is not an object", "[3]", "?")):
                gh.run = fake(answer)
                check(label, br.pull_requests("h") == want, repr(br.pull_requests("h")))
        finally:
            gh.run = real

        print("a pull request's head is the remote branch the local one tracks")
        sh(wc, "config", "branch.owed.remote", "origin")
        sh(wc, "config", "branch.owed.merge", "refs/heads/h/l/feat/x")
        os.chdir(wc)
        try:
            check("tracked under another name", br.pr_head("owed") == "h/l/feat/x")
            check("not tracking: its own name", br.pr_head("merged") == "merged")
        finally:
            os.chdir(cwd)

        print("a git call that fails is never an answer, and never a deletion")
        # Each wrapper fails one git subcommand and runs the rest as git.
        def failing(sub: str) -> str:
            d = os.path.join(scratch, "fail-" + sub)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "git"), "w") as fh:
                fh.write(f'#!/bin/sh\nfor a in "$@"; do [ "$a" = {sub} ] && {{ echo "fatal: injected" >&2; exit 128; }}; done\nexec {GIT} "$@"\n')
            os.chmod(os.path.join(d, "git"), 0o755)
            return d

        wc = fixture("fail-count")
        r = fabric(wc, "--sweep", path_first=failing("rev-list"))
        check("no count: nothing deleted, the branch shows ?", "merged" in branches_of(wc) and
              any(l.split()[:2] == ["?", "merged"] for l in r.stdout.splitlines()), r.stdout + r.stderr)
        check("...and nothing is `deleted`", "deleted " not in r.stdout)

        wc = fixture("fail-wtlist")
        r = fabric(wc, "--sweep", path_first=failing("worktree"))
        check("no worktree list: exit 2, nothing deleted", r.returncode == 2 and "merged" in branches_of(wc), r.stdout + r.stderr)

        wc = fixture("fail-refs")
        r = fabric(wc, "--sweep", path_first=failing("for-each-ref"))
        check("no branch list: exit 2", r.returncode == 2 and "injected" in r.stderr, r.stdout + r.stderr)

        wc = fixture("fail-status")
        r = fabric(wc, "--sweep", path_first=failing("status"))
        check("no status: exit 2, nothing deleted", r.returncode == 2 and "merged" in branches_of(wc), r.stdout + r.stderr)

        wc = fixture("fail-wtstatus")
        bad = os.path.join(scratch, "wt-bad")
        sh(wc, "worktree", "add", "-q", bad, "-b", "wt-bad", "main")
        d = os.path.join(scratch, "fail-wtstatus-bin")
        os.makedirs(d)
        with open(os.path.join(d, "git"), "w") as fh:
            fh.write(f'#!/bin/sh\ncase "$*" in *wt-bad*status*) echo "fatal: injected" >&2; exit 128;; esac\nexec {GIT} "$@"\n')
        os.chmod(os.path.join(d, "git"), 0o755)
        r = fabric(wc, "--sweep", path_first=d)
        check("a worktree whose status cannot be read is kept with the reason, not removed",
              os.path.isdir(bad) and "status unreadable" in r.stdout and "removed worktree" not in r.stdout
              and "wt-bad" in branches_of(wc), r.stdout + r.stderr)

        wc = fixture("fail-delete")
        d = os.path.join(scratch, "fail-delete-bin")
        os.makedirs(d)
        with open(os.path.join(d, "git"), "w") as fh:
            fh.write(f'#!/bin/sh\nfor a in "$@"; do [ "$a" = -D ] && {{ echo "error: injected" >&2; exit 1; }}; done\nexec {GIT} "$@"\n')
        os.chmod(os.path.join(d, "git"), 0o755)
        r = fabric(wc, "--sweep", path_first=d)
        check("a deletion git refuses is KEPT, with git's words", "KEPT merged" in r.stdout and "injected" in r.stderr
              and "merged" in branches_of(wc), r.stdout + r.stderr)

        wc = fixture("fail-fetch")
        sh(wc, "remote", "set-url", "origin", os.path.join(scratch, "nowhere.git"))
        r = fabric(wc, "--sweep")
        check("a failed fetch: exit 2, nothing deleted", r.returncode == 2 and "merged" in branches_of(wc)
              and "fetch origin failed" in r.stderr, r.stdout + r.stderr)

        print("what a sweep may delete")
        wc = fixture("sweep")
        sh(wc, "update-ref", "refs/heads/-x", "main")
        sh(wc, "update-ref", "refs/heads/--help", "main")
        sh(wc, "checkout", "-q", "-b", "current-at-zero", "main")
        r = fabric(wc, "--sweep")
        left = branches_of(wc)
        check("exit 0", r.returncode == 0, r.stdout + r.stderr)
        check("a branch wholly on main is deleted, with its sha", "merged" not in left and "deleted merged (" in r.stdout)
        check("the current branch is never deleted, though at 0", "current-at-zero" in left, r.stdout)
        check("main is never deleted", "main" in left)
        check("a branch with a commit off main is kept", "owed" in left)
        check("a branch named like an option is kept, and git is not handed it",
              "-x" in left and "--help" in left and "KEPT -x" in r.stdout and "KEPT --help" in r.stdout
              and "usage:" not in r.stdout + r.stderr and "fatal" not in r.stderr, r.stdout + r.stderr)
        check("the sweep is recorded under the toplevel",
              os.path.realpath(wc) in json.load(open(os.path.join(state, "agents", br.load_identity().current_agent(),
                                                                  "branch-sweep.json"))))
        r = fabric(wc)
        check("a report alone deletes nothing", r.returncode == 0 and "safe to delete (0):" in r.stdout)
        sh(wc, "branch", "again", "main")
        r = fabric(wc)
        safe = [l for l in r.stdout.splitlines() if l.startswith("safe to delete (0):")][0]
        check("the current branch is not offered as safe to delete", "current-at-zero" not in safe and "again" in safe, safe)

        print("the deletion recounts, whatever the report said")
        wc = fixture("recount")
        os.chdir(wc)
        try:
            check("a branch that has commits off main is KEPT when handed over", br.sweep_one("owed", set(), "origin/main") == "KEPT owed"
                  and "owed" in branches_of(wc))
            check("a branch that cannot be counted is KEPT", br.sweep_one("nope", set(), "origin/main") == "KEPT nope")
            check("a checked-out branch is KEPT with the reason", br.sweep_one("merged", {"merged"}, "origin/main").startswith("KEPT merged — checked out")
                  and "merged" in branches_of(wc))
            real_run = br.git.run

            def never(*a, **k):
                raise AssertionError("git was asked")
            br.git.run = never
            try:
                kept_x = br.sweep_one("-x", set(), "origin/main")
            except AssertionError:
                kept_x = "git was asked"
            finally:
                br.git.run = real_run
            check("a name that starts with - is KEPT without asking git", kept_x == "KEPT -x", kept_x)
            check("a merged branch is deleted, with its sha", br.sweep_one("merged", set(), "origin/main").startswith("deleted merged (")
                  and "merged" not in branches_of(wc))
        finally:
            os.chdir(cwd)

        print("a detached HEAD")
        wc = fixture("detached")
        sh(wc, "checkout", "-q", "--detach", "merged")
        r = fabric(wc, "--sweep")
        check("is named, and every branch at 0 may go", "on: (detached)" in r.stdout and "merged" not in branches_of(wc), r.stdout + r.stderr)

        print("a squash-merged branch has commits off main: kept, and its merged PR said")
        wc = fixture("squash")
        tool("gh", """echo '[{"number":3,"state":"MERGED"}]'\n""")
        r = fabric(wc, "--sweep", path_first=bindir)
        check("kept", "owed" in branches_of(wc) and "kept, with commits off main: owed" in r.stdout, r.stdout)
        check("the person's decision is said", "owed — pull request: #3 MERGED" in r.stdout
              and "squashed or rewritten" in r.stdout, r.stdout)
        tool("gh", "exit 1\n")
        r = fabric(wc, path_first=bindir)
        check("a gh that fails reads ?, not none", "owed — pull request: ?" in r.stdout, r.stdout)

        print("no origin/main, an unknown argument, outside a working copy, help")
        wc = os.path.join(scratch, "empty")
        sh(scratch, "init", "-q", "-b", "main", wc)
        sh(wc, "remote", "add", "origin", os.path.join(scratch, "empty-origin.git"))
        sh(scratch, "init", "-q", "--bare", "-b", "main", os.path.join(scratch, "empty-origin.git"))
        r = fabric(wc, "--sweep")
        check("no default branch known (origin/HEAD unset, no registry entry): exit 2, said, nothing counted",
              r.returncode == 2 and "the default branch of origin is unknown" in r.stderr, r.stdout + r.stderr)
        # Known, and absent on origin: origin/HEAD names a branch the remote has not got.
        sh(wc, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        r = fabric(wc, "--sweep")
        check("no origin/main: exit 2", r.returncode == 2 and "no origin/main here" in r.stderr, r.stdout + r.stderr)
        r = fabric(wc, "--nope")
        check("unknown argument: exit 2", r.returncode == 2 and "unknown argument '--nope' (--sweep)" in r.stderr)
        r = fabric(wc, "", "--sweep")
        check("only the first argument is read", r.returncode == 2 and "unknown argument" not in r.stderr)
        r = fabric(scratch)
        check("outside a working copy: exit 2", r.returncode == 2 and "not in a git working copy" in r.stderr)
        r = fabric(scratch, "--help")
        check("help: exit 0, from stdout", r.returncode == 0 and r.stdout.startswith("bin/fabric-branches —")
              and r.stdout.rstrip().endswith("old.") and r.stderr == "")

        print("reached through a symlink in another directory, as ~/.local/bin reaches it")
        linkdir = os.path.join(scratch, "local-bin")
        os.makedirs(linkdir)
        link = os.path.join(linkdir, "fabric-branches")
        os.symlink(SHIM, link)
        wc = fixture("linked")
        for how, argv in (("by path", ["bash", link]), ("by PATH", ["fabric-branches"])):
            e = clean_env(AGENT_FABRIC_STATE_DIR=state)
            e["PATH"] = linkdir + os.pathsep + e["PATH"]
            r = subprocess.run([*argv, "--sweep"], cwd=wc, capture_output=True, text=True, env=e, timeout=120)
            check(f"a sweep {how} runs the module and records itself",
                  r.returncode == 0 and "working copy:" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr)
        r = subprocess.run(["fabric-branches", "--help"], cwd=scratch, capture_output=True, text=True, env=e, timeout=120)
        check("help through the link", r.returncode == 0 and r.stdout.startswith("bin/fabric-branches —"))

        print("a closed stdout ends the run quietly")
        wc = fixture("pipe")
        rd, wr = os.pipe()
        os.close(rd)
        rc = subprocess.run(["bash", SHIM, "--sweep"], cwd=wc, stdout=wr, stderr=subprocess.DEVNULL,
                            env=clean_env(AGENT_FABRIC_STATE_DIR=state), timeout=120).returncode
        os.close(wr)
        check("141", rc == 141, str(rc))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print("a module in the caller's directory never runs under a bin/ shim (review of #73)")
    evil = tempfile.mkdtemp(prefix="test_branches_evil.")
    try:
        with open(os.path.join(evil, "json.py"), "w") as f:
            f.write("print('PLANTED')\nraise SystemExit(9)\n")
        for cmd, arg in (("fabric-branches", "--help"), ("fabric-status", "--help"), ("fabric-lease", "--help"),
                         ("fabric-host", "list")):
            r = subprocess.run(["bash", os.path.join(HERE, "bin", cmd), arg], cwd=evil, capture_output=True,
                               text=True, timeout=60, stdin=subprocess.DEVNULL)
            check(f"{cmd}: a json.py beside the caller is not imported", "PLANTED" not in r.stdout + r.stderr
                  and r.returncode != 9, r.stdout[-200:])
    finally:
        shutil.rmtree(evil, ignore_errors=True)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
