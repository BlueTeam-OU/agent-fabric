#!/usr/bin/env python3
"""tools/fabric/review_mcp/ and bin/fabric-review-mcp (agent-fabric ADR-065 §2 A and B): one case per threat the review tools are built
against, each with its positive control (the same thing done without the guard does happen), and the real server over stdio as Claude
Code runs it. The sandbox cases need unprivileged user namespaces; where the host refuses them (CI's Ubuntu 24.04) they print a `skip`
line saying so and are not counted as passed. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()

from review_mcp import gittools, runner, sandbox, scope, server as srv  # noqa: E402
import review_brief  # noqa: E402
from github import review_coverage  # noqa: E402

BIN = os.path.join(HERE, "bin", "fabric-review-mcp")
fails = 0
# A sleep the cases start has a duration no other run uses, so a process an earlier, killed run left behind is not taken for this one's.
TAG = str(os.getpid())


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("  ok    " if ok else "  FAIL  ") + label + ("" if ok else f"\n        {detail[:600]}"))
    fails += 0 if ok else 1


def skip(label: str, why: str) -> None:
    print(f"  skip  {label}: {why}")


def sh(argv: list[str], cwd: str, timeout: int = 60) -> str:
    """A fixture command, in an environment of its own: the session's git config would sign these commits."""
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"], "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    return subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def alive(pid: int) -> bool:
    """A zombie is not alive: the container's pid 1 may not reap what a killed group leaves."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def processes_with(needle: str) -> list[int]:
    found = []
    for name in os.listdir("/proc"):
        if name.isdigit() and int(name) != os.getpid():
            try:
                with open(f"/proc/{name}/cmdline", "rb") as fh:
                    if needle.encode() in fh.read() and alive(int(name)):
                        found.append(int(name))
            except OSError:
                pass
    return found


def userns_refused() -> str | None:
    p = subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"],
                       capture_output=True, text=True, timeout=30)
    return None if p.returncode == 0 else (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[0]


def main() -> int:
    scratch = os.path.realpath(tempfile.mkdtemp(prefix="test_review_mcp."))
    atexit.register(shutil.rmtree, scratch, True)
    home = os.path.join(scratch, "home")
    for d in (home, os.path.join(home, "tmp"), os.path.join(home, ".ssh"), os.path.join(home, ".config", "agent-fabric"), os.path.join(scratch, "marks")):
        os.makedirs(d)
    # The suite's own environment, not the session's or the runner's: a secret planted to prove a child never sees it, and nothing else.
    os.environ.clear()
    os.environ.update({"PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": os.path.join(home, "tmp"), "LANG": "C.UTF-8",
                       "FABRIC_TEST_API_TOKEN": "hostile-secret-value", "GIT_EXTERNAL_DIFF": os.path.join(scratch, "mark.sh")})
    tempfile.tempdir = None
    secret_file = os.path.join(home, ".config", "agent-fabric", "secrets.env")
    ssh_file = os.path.join(home, ".ssh", "id_ed25519")
    for f in (secret_file, ssh_file):
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("PLANTED-SECRET-CONTENT\n")
    mark = os.path.join(scratch, "mark.sh")
    with open(mark, "w", encoding="utf-8") as fh:
        fh.write(f'#!/bin/sh\ntouch "{scratch}/marks/$1"\n[ "$1" = textconv ] && cat "$2"\nexit 0\n')
    os.chmod(mark, 0o755)
    marks = os.path.join(scratch, "marks")

    clone = os.path.join(home, "work", "clone")
    os.makedirs(clone)
    sh(["git", "init", "-q", "-b", "main", clone], scratch)
    with open(os.path.join(clone, "f.txt"), "w") as fh:
        fh.write("one\n")
    sh(["git", "add", "."], clone)
    sh(["git", "commit", "-q", "-m", "base"], clone)
    base = sh(["git", "rev-parse", "HEAD"], clone)
    with open(os.path.join(clone, "f.txt"), "w") as fh:
        fh.write("two\n")
    with open(os.path.join(clone, ".gitattributes"), "w") as fh:
        fh.write("*.txt diff=evil\n")          # the pull request's attributes, checked out in the session's clone as its branch is
    sh(["git", "add", "."], clone)
    sh(["git", "commit", "-q", "-m", "head"], clone)
    head = sh(["git", "rev-parse", "HEAD"], clone)
    sh(["git", "branch", "dup", base], clone)
    sh(["git", "tag", "dup", head], clone)
    sh(["git", "worktree", "add", "-q", "--detach", os.path.join(home, "work", "wt"), base], clone)
    other = os.path.join(home, "work", "other")
    sh(["git", "init", "-q", other], scratch)
    sh(["git", "commit", "-q", "--allow-empty", "-m", "x"], other)
    os.environ["CLAUDE_PROJECT_DIR"] = clone
    evidence = review_brief.evidence_path(review_brief.repo_name_of(clone), head)
    os.makedirs(os.path.dirname(evidence), exist_ok=True)
    sh(["git", "worktree", "add", "-q", "--detach", evidence, head], clone)
    server = srv.Server()

    def call(name: str, **args) -> tuple[bool, str]:
        r = server.call(name, args)
        return r["isError"], r["content"][0]["text"]

    print("-- option injection: a leading \"-\" in every field")
    valid = {"review_diff": {"base": base, "head": head, "pathspec": "f.txt"},
             "review_log": {"head": head, "base": base, "path": "f.txt"},
             "review_show": {"rev": head, "path": "f.txt"},
             "review_blame": {"rev": head, "path": "f.txt", "line_start": 1},
             "review_grep": {"rev": head, "pattern": "two", "pathspec": "f.txt"},
             "review_check": {"head": head, "argv": ["true"]}}
    for tool, args in valid.items():
        if tool != "review_check":
            err, text = call(tool, **args)
            check(f"{tool}: the valid call works (positive control)", not err, text)
        for key, value in args.items():
            if isinstance(value, str):
                err, text = call(tool, **{**args, key: "-x"})
                check(f"{tool}.{key} = \"-x\" is refused", err and "may not start with" in text, text)
        err, text = call(tool, **{**args, "repository": "-x"})
        check(f"{tool}.repository = \"-x\" is refused", err and "may not start with" in text, text)
    err, text = call("review_check", head=head, argv=["-c", "true"])
    check("review_check: argv[0] = \"-c\" is refused", err and "may not start with" in text, text)
    err, text = call("review_diff", base=base, head=head, pathspec=[":(top)f.txt"])
    check("a pathspec that begins with magic is refused", err and "pathspec magic" in text, text)
    err, text = call("review_show", rev=head, path="../x")
    check("a path that climbs out of the tree is refused", err and "inside the repository" in text, text)

    print("-- revisions: resolved by git, ambiguity refused, the id used")
    err, text = call("review_log", head="no-such-ref")
    check("an unresolvable rev is refused", err and "does not name a commit" in text, text)
    err, text = call("review_show", rev=f"{head}:f.txt")
    check("a rev that names a blob, not a commit, is refused", err and "does not name a commit" in text, text)
    err, text = call("review_log", head="dup")
    check("a name that is a branch and a tag is refused as ambiguous", err and "ambiguous" in text, text)
    err, text = call("review_log", head="refs/tags/dup", max_count=1)
    check("the same name spelled in full resolves (positive control)", not err and text.startswith(head), text)
    seen: list[tuple[str, ...]] = []
    real_run_git = gittools.run_git

    def recording(repo, *a, **kw):
        seen.append(a)
        return real_run_git(repo, *a, **kw)
    gittools.run_git = recording
    try:
        call("review_log", head="main", max_count=1)
    finally:
        gittools.run_git = real_run_git
    log_args = next(a for a in seen if a[0] == "log")
    check("the commit id git resolved reaches the command, not the text given", head in log_args and "main" not in log_args, str(log_args))

    print("-- repository: the session clone or one of its worktrees")
    err, text = call("review_log", head="HEAD", repository=other)
    check("a repository that is not the clone is refused", err and "not the session's clone" in text, text)
    err, text = call("review_log", head="HEAD", repository=os.path.join(clone, ".git"))
    check("the clone's .git directory is not its toplevel and is refused", err and "not the session's clone" in text, text)
    err, text = call("review_log", head="HEAD", repository=os.path.join(home, "work", "wt"), max_count=1)
    check("a worktree of the clone is allowed (positive control)", not err, text)
    err, text = call("review_log", head="HEAD", repository=clone, max_count=1)
    check("the clone itself is allowed (positive control)", not err, text)
    os.environ["CLAUDE_PROJECT_DIR"] = os.path.join(clone, "..", "other")
    err, text = call("review_log", head="HEAD", repository=clone)
    check("the clone is whatever CLAUDE_PROJECT_DIR names: another one makes this a foreign repository", err, text)
    os.environ.pop("CLAUDE_PROJECT_DIR")
    err, text = call("review_log", head="HEAD")
    check("without CLAUDE_PROJECT_DIR nothing is allowed", err and "CLAUDE_PROJECT_DIR" in text, text)
    os.environ["CLAUDE_PROJECT_DIR"] = clone

    print("-- program-running config: a repository-local key, the pull request's attributes, the environment")
    keys = (("diff.evil.textconv", f"{mark} textconv"), ("diff.external", f"{mark} external"))
    sh(["git", "config", "diff.evil.textconv", f"{mark} textconv"], clone)
    plain = ["git", "-c", "core.attributesFile=/dev/null", "diff", base, head]
    sh(plain, clone)
    check("control: plain git with the attribute and the config runs the textconv driver", os.path.exists(os.path.join(marks, "textconv")))
    os.unlink(os.path.join(marks, "textconv"))
    err, text = call("review_diff", base=base, head=head)
    check("review_diff over the same clone runs no driver, and still shows the change", not err and "+two" in text
          and not os.path.exists(os.path.join(marks, "textconv")), text)
    err, text = call("review_log", head=head, base=base, patch=True)
    check("review_log -p runs no driver", not err and not os.path.exists(os.path.join(marks, "textconv")), text)
    err, text = call("review_show", rev=head)
    check("review_show runs no driver", not err and not os.path.exists(os.path.join(marks, "textconv")), text)
    err, text = call("review_blame", rev=head, path="f.txt", line_start=1)
    check("review_blame runs no driver", not err and not os.path.exists(os.path.join(marks, "textconv")), text)
    sh(["git", "config", "--unset", "diff.evil.textconv"], clone)
    sh(["git", "config", "diff.external", f"{mark} external"], clone)
    sh(["git", "diff", base, head], clone)
    check("control: plain git with diff.external set runs it", os.path.exists(os.path.join(marks, "external")))
    os.unlink(os.path.join(marks, "external"))
    err, text = call("review_diff", base=base, head=head)
    check("review_diff with diff.external set (config and GIT_EXTERNAL_DIFF) runs no program", not err and "+two" in text
          and not os.path.exists(os.path.join(marks, "external")), text)
    sh(["git", "config", "--unset", "diff.external"], clone)
    with open(os.path.join(home, ".gitconfig"), "w") as fh:
        fh.write(f"[diff]\n\texternal = {mark} globalext\n")
    plain_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.path.join(home, ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "-C", clone, "diff", base, head], env={k: v for k, v in plain_env.items() if k != "GIT_EXTERNAL_DIFF"},
                   capture_output=True, timeout=30)
    check("control: plain git reads a global config that names a diff program", os.path.exists(os.path.join(marks, "globalext")))
    os.unlink(os.path.join(marks, "globalext"))
    os.environ["XDG_CONFIG_HOME"] = home
    err, text = call("review_diff", base=base, head=head)
    del os.environ["XDG_CONFIG_HOME"]
    check("a global config that names a diff program is not read", not err and not os.path.exists(os.path.join(marks, "globalext")), text)
    del keys
    pinned = gittools.git_argv("/r", "log")
    for key in ("core.fsmonitor=false", "core.hooksPath=/dev/null", "core.pager=cat", "core.attributesFile=/dev/null", "diff.external=",
                "protocol.allow=never"):
        check(f"git is run with -c {key}", "-c" in pinned and key in pinned, str(pinned))
    check("git is run with --no-pager and the empty tree as attribute source",
          "--no-pager" in pinned and f"--attr-source={gittools.EMPTY_TREE}" in pinned, str(pinned))
    for verb, fn in (("diff", gittools.review_diff), ("log", gittools.review_log), ("show", gittools.review_show)):
        seen.clear()
        gittools.run_git = recording
        try:
            fn({"base": base, "head": head, "rev": head})
        finally:
            gittools.run_git = real_run_git
        used = next(a for a in seen if a[0] == verb)
        check(f"git {verb} is run with --no-ext-diff and --no-textconv", "--no-ext-diff" in used and "--no-textconv" in used, str(used))
    seen.clear()
    gittools.run_git = recording
    try:
        gittools.review_blame({"rev": head, "path": "f.txt", "line_start": 1})
        gittools.review_show({"rev": head, "path": "f.txt"})
    finally:
        gittools.run_git = real_run_git
    check("git blame and git show of a file are run with --no-textconv",
          all("--no-textconv" in a for a in seen if a[0] in ("blame", "show")), str(seen))

    print("-- config keys that name a FILE: a pull request's symlink at that path is not followed (round 1 C1)")
    wt = os.path.join(home, "work", "wt")
    leak_dir = os.path.join(scratch, "leak")
    os.makedirs(leak_dir)
    marker_rev, marker_map, marker_order = (os.path.join(leak_dir, n) for n in ("revs", "map", "order"))
    with open(marker_rev, "w", encoding="utf-8") as fh:
        fh.write("LEAKMARKER-REVS\n")
    with open(marker_map, "w", encoding="utf-8") as fh:
        fh.write("LEAKMARKER-NAME <t@e>\n")
    with open(marker_order, "w", encoding="utf-8") as fh:
        fh.write("b.txt\na.txt\n")
    for name, target in (("pr-revs", marker_rev), ("pr-map", marker_map), ("pr-order", marker_order)):
        os.symlink(target, os.path.join(clone, name))         # the pull request's tree, as its branch is checked out in the session's clone
        os.symlink(target, os.path.join(wt, name))
    for key, value in (("blame.ignoreRevsFile", "pr-revs"), ("mailmap.file", "pr-map"), ("diff.orderFile", "pr-order")):
        sh(["git", "config", key, value], clone)       # a worktree shares the clone's config
    for n in ("a.txt", "b.txt", "é a.txt", "sp ace.txt"):
        with open(os.path.join(wt, n), "w", encoding="utf-8") as fh:
            fh.write("x\n")
    sh(["git", "add", "a.txt", "b.txt", "é a.txt", "sp ace.txt"], wt)
    sh(["git", "commit", "-q", "-m", "files"], wt)
    tip = sh(["git", "rev-parse", "HEAD"], wt)
    plain_blame = subprocess.run(["git", "-C", clone, "blame", "-L1,1", head, "--", "f.txt"], capture_output=True, text=True, timeout=30)
    check("control: plain git blame reads blame.ignoreRevsFile through the symlink and quotes its first line",
          "LEAKMARKER-REVS" in plain_blame.stderr, plain_blame.stdout + plain_blame.stderr)
    with open(marker_rev, "w", encoding="utf-8") as fh:
        fh.write(f"{base}\n")
    plain_blame = subprocess.run(["git", "-C", clone, "blame", "-L1,1", head, "--", "f.txt"], capture_output=True, text=True, timeout=30)
    check("control: plain git blame shows the author name the symlinked mailmap.file gives", "LEAKMARKER-NAME" in plain_blame.stdout, plain_blame.stdout)
    plain_order = sh(["git", "-C", wt, "diff", "--name-only", base, tip], scratch).splitlines()
    check("control: plain git diff orders by the symlinked diff.orderFile", plain_order.index("b.txt") < plain_order.index("a.txt"), str(plain_order))
    # The marker of the revs file is first an invalid object name (the error that quoted it), then a real commit (the ignore list that
    # changes what blame shows); neither may be seen through the tool.
    for shape in ("LEAKMARKER-REVS\n", f"{base}\n"):
        with open(marker_rev, "w", encoding="utf-8") as fh:
            fh.write(shape)
        err, text = call("review_blame", rev=head, path="f.txt", line_start=1)
        check(f"review_blame with blame.ignoreRevsFile at a symlink ({shape.strip()[:14]}): ok, the file is not read, no marker in the result",
              not err and "LEAKMARKER" not in text and text.split()[0].lstrip("^").startswith(head[:7]), text)
    err, text = call("review_blame", rev=head, path="f.txt", line_start=1)
    check("review_blame with mailmap.file at a symlink: the mailmap name is not applied", not err and "LEAKMARKER-NAME" not in text, text)
    err, text = call("review_log", head=head, base=base, patch=True)
    check("review_log -p with mailmap.file at a symlink: the mailmap name is not applied", not err and "LEAKMARKER-NAME" not in text, text)
    err, text = call("review_diff", base=base, head=tip, output="name-only", repository=wt)
    check("review_diff with diff.orderFile at a symlink: the order file is not read (a.txt before b.txt)",
          not err and text.splitlines().index("a.txt") < text.splitlines().index("b.txt"), text)
    for tool, args in (("review_diff", {"base": base, "head": head}), ("review_log", {"head": head}), ("review_show", {"rev": head}),
                       ("review_grep", {"rev": head, "pattern": "two"}), ("review_blame", {"rev": head, "path": "f.txt", "line_start": 1})):
        err, text = call(tool, **args)
        check(f"{tool}: no marker of the three symlinked files in its result", not err and "LEAKMARKER" not in text, text)
    for key in ("mailmap.file=", "mailmap.blob=", "diff.orderFile=/dev/null", "core.excludesFile=/dev/null", "core.quotePath=false", "diff.renames=true"):
        check(f"git is run with -c {key}", key in gittools.git_argv("/r", "log"), key)
    seen.clear()
    gittools.run_git = recording
    try:
        gittools.review_blame({"rev": head, "path": "f.txt", "line_start": 1})
    finally:
        gittools.run_git = real_run_git
    check("git blame is run with --no-ignore-revs-file (a -c cannot clear the list)", any("--no-ignore-revs-file" in a for a in seen if a[0] == "blame"), str(seen))
    for key in ("blame.ignoreRevsFile", "mailmap.file", "diff.orderFile"):
        sh(["git", "config", "--unset", key], clone)

    print("-- paths are printed as written, so a coverage block copied from the output is the set post-review compares (round 1 R3)")
    wanted = set(review_coverage.diff_paths(wt, base, tip))
    check("control: review_coverage.diff_paths holds the non-ASCII and the space-bearing path", {"é a.txt", "sp ace.txt"} <= wanted, str(wanted))
    quoted = subprocess.run(["git", "-C", wt, "diff", "--name-only", base, tip], capture_output=True, text=True, timeout=30).stdout
    check("control: plain git diff --name-only quotes the non-ASCII path", '"\\303\\251 a.txt"' in quoted, quoted)
    err, text = call("review_diff", base=base, head=tip, output="name-only", repository=wt)
    check("review_diff name-only lists exactly the paths diff_paths lists", not err and set(text.splitlines()) == wanted, text)
    err, text = call("review_diff", base=base, head=tip, output="name-status", repository=wt)
    check("review_diff name-status lists exactly the paths diff_paths lists", not err and {ln.split("\t", 1)[1] for ln in text.splitlines()} == wanted, text)
    err, text = call("review_diff", base=base, head=tip, output="stat", repository=wt)
    check("review_diff stat names the non-ASCII path as written", not err and "é a.txt" in text and "\\303" not in text, text)
    err, text = call("review_grep", rev=tip, pattern="x", fixed=True, repository=wt)
    check("review_grep names the non-ASCII path as written", not err and "é a.txt" in text and "\\303" not in text, text)

    print("-- the environment of a child")
    dump = os.path.join(scratch, "envdump")
    fake_git = os.path.join(scratch, "fake-git")
    with open(fake_git, "w") as fh:
        fh.write(f'#!/bin/sh\nenv > "{dump}"\nexit 1\n')
    os.chmod(fake_git, 0o755)
    gittools.GIT = fake_git
    try:
        call("review_log", head="HEAD")
    finally:
        gittools.GIT = "git"
    dumped = open(dump, encoding="utf-8").read()
    check("control: the process holds the secret, and git's child gets PATH", os.environ["FABRIC_TEST_API_TOKEN"] and "PATH=" in dumped)
    check("a secret of the process is not in the git child's environment", "hostile-secret-value" not in dumped and "FABRIC_TEST_API_TOKEN" not in dumped
          and "GIT_EXTERNAL_DIFF" not in dumped, dumped)
    check("the child's environment pins git off the system and global config", "GIT_CONFIG_NOSYSTEM=1" in dumped and "GIT_CONFIG_GLOBAL=/dev/null" in dumped, dumped)
    check("CLEAN_ENV is the review guard's own list", scope.clean_env_names() == ast_clean_env(), str(scope.clean_env_names()))
    try:
        scope.clean_env_names(os.path.join(scratch, "no-such-guard.py"))
        check("an unreadable guard file refuses to start a child", False)
    except scope.ToolError:
        check("an unreadable guard file refuses to start a child", True)

    print("-- output cap and wall budget")
    ran = runner.run_bounded(["/usr/bin/yes"], {"PATH": "/usr/bin"}, scratch, 20, 1000)
    check("a flood is cut at the cap, and the child is ended", ran.cut and len(ran.out) == 1000 and ran.returncode is None)
    check("the cut is said in the text", "output cut at 1000 bytes" in runner.text_of(ran.out, 1000, True))
    ran = runner.run_bounded(["/usr/bin/printf", "abc"], {"PATH": "/usr/bin"}, scratch, 20, 1000)
    check("control: output under the cap is whole and unmarked", not ran.cut and ran.out == b"abc" and ran.returncode == 0)
    pidfile = os.path.join(scratch, "child.pid")
    t0 = time.monotonic()
    ran = runner.run_bounded(["/bin/sh", "-c", f'sleep 4711.{TAG} & echo $! > "{pidfile}"; wait'], {"PATH": "/usr/bin:/bin"}, scratch, 1, 1000)
    child = int(open(pidfile, encoding="utf-8").read())
    time.sleep(0.2)
    check("a program that outlives its budget is ended at it", ran.timed_out and time.monotonic() - t0 < 10)
    check("its whole process group is ended, the forked child too", not alive(child) and not processes_with(f"4711.{TAG}"), str(child))
    ran = runner.run_bounded(["/bin/sh", "-c", f'sleep 4712.{TAG} & echo $! > "{pidfile}"; exit 0'], {"PATH": "/usr/bin:/bin"}, scratch, 20, 1000)
    child = int(open(pidfile, encoding="utf-8").read())
    time.sleep(0.2)
    check("a child left behind by a program that exited is ended with the group, and the exit is kept",
          ran.returncode == 0 and not ran.timed_out and not alive(child), str(child))
    gittools.CAP_BYTES, gittools.BUDGET_S = 200, 20.0
    try:
        err, text = call("review_log", head=head, max_count=1000, patch=True)
        check("a tool's result says it was cut", not err and "output cut at 200 bytes" in text, text)
    finally:
        gittools.CAP_BYTES, gittools.BUDGET_S = 100_000, 30.0
    slow = os.path.join(scratch, "slow-git")
    with open(slow, "w") as fh:
        fh.write(f"#!/bin/sh\nexec sleep 4714.{TAG}\n")
    os.chmod(slow, 0o755)
    gittools.GIT, gittools.BUDGET_S = slow, 1.0
    try:
        t0 = time.monotonic()
        err, text = call("review_log", head="HEAD")
        check("a git that outlives the budget is a refusal that says so", err and "did not finish within" in text and time.monotonic() - t0 < 10, text)
    finally:
        gittools.GIT, gittools.BUDGET_S = "git", 30.0

    print("-- review_check: the sandbox's arguments")
    common = subprocess.run(["git", "-C", clone, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True,
                            timeout=30).stdout.strip()
    own = subprocess.run(["git", "-C", evidence, "rev-parse", "--path-format=absolute", "--git-dir"], capture_output=True, text=True,
                         timeout=30).stdout.strip()
    argv = sandbox.bwrap_argv("bwrap", evidence, common, own, ["true"])
    for opt in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
        check(f"the sandbox is run with {opt}", opt in argv, str(argv))
    check("no namespace is shared back: nothing names --share-net", not any(a.startswith("--share") for a in argv), str(argv))
    check("the git directory is bound by an allowlist: no bind of the common directory itself, none of its config, hooks or logs",
          common not in [argv[i + 2] for i, a in enumerate(argv) if a == "--ro-bind"] and
          not any(os.path.join(common, n) == a for n in ("config", "config.worktree", "hooks", "logs", "info") for a in argv), str(argv))
    check("and the objects, the refs and the worktree's own HEAD are bound read-only",
          all(x in argv and argv[argv.index(x) - 1] == "--ro-bind" for x in (os.path.join(common, "objects"), os.path.join(common, "refs"), os.path.join(own, "HEAD"))), str(argv))
    check("TMPDIR is /tmp and /tmp, /dev and /proc are made new",
          argv[argv.index("TMPDIR") - 1:argv.index("TMPDIR") + 2] == ["--setenv", "TMPDIR", "/tmp"]
          and all(x in argv for x in ("--dev", "--proc")) and argv[argv.index("--tmpfs") + 1] == "/tmp", str(argv))
    check("the only writable bind is none: every bind of the worktree and the object store is read-only",
          "--bind" not in argv and "--dev-bind" not in argv and argv[argv.index(evidence) - 1] == "--ro-bind", str(argv))

    print("-- review_check: the proved sandbox")
    why = userns_refused()
    if why:
        skip("review_check cases", f"this host refuses unprivileged user namespaces ({why})")
    else:
        sandbox_cases(server, call, head, base, clone, evidence, scratch, home, secret_file, ssh_file, marks)

    print("-- the server over stdio")
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": clone, "HOME": home, "AGENT_FABRIC_PYTHON": sys.executable}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "review_log", "arguments": {"head": head, "max_count": 1}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "review_log", "arguments": {"head": "-x"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"}]
    r = subprocess.run([BIN], input="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n", env=env, capture_output=True, text=True, timeout=60)
    out = [json.loads(ln) for ln in r.stdout.splitlines()]
    by = {o.get("id"): o for o in out}
    check("exit 0 at end of input, stderr empty", r.returncode == 0 and r.stderr == "", r.stderr)
    check("initialize names the server fabric-review", by[1]["result"]["serverInfo"]["name"] == "fabric-review", str(by[1]))
    check("the notification gets no answer: five requests and one bad line, six answers", len(out) == 6, str(len(out)))
    check("tools/list: the six tools, each with an input schema",
          [t["name"] for t in by[2]["result"]["tools"]] == ["review_diff", "review_log", "review_show", "review_blame", "review_grep", "review_check"]
          and all(t["inputSchema"]["type"] == "object" for t in by[2]["result"]["tools"]), str(by[2]))
    check("tools/call: a log of the head", by[3]["result"]["isError"] is False and by[3]["result"]["content"][0]["text"].startswith(head))
    check("a refusal is a result with isError, not a protocol error", by[4]["result"]["isError"] is True and "error" not in by[4])
    check("an unknown method is -32601; a line that is not JSON is -32700 with a null id",
          by[5]["error"]["code"] == -32601 and by[None]["error"]["code"] == -32700, str(by))

    print("test_review_mcp:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


def ast_clean_env() -> tuple[str, ...]:
    """CLEAN_ENV as the guard's own text assigns it, found without scope.py's reader."""
    import ast
    with open(scope.GUARD, encoding="utf-8") as fh:
        for node in ast.parse(fh.read()).body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "CLEAN_ENV":
                return tuple(ast.literal_eval(node.value))
    return ()


def fresh(tool: str, **args) -> tuple[bool, str]:
    """A server of its own: the proofs of the one the other cases used are not the proofs of this one."""
    r = srv.Server().call(tool, args)
    return r["isError"], r["content"][0]["text"]


def sandbox_cases(server, call, head, base, clone, evidence, scratch, home, secret_file, ssh_file, marks) -> None:
    def run(*argv: str, **kw) -> tuple[bool, str]:
        return call("review_check", head=head, argv=list(argv), **kw)

    def exit_of(text: str) -> str:
        return text.splitlines()[0]

    py = "/usr/bin/python3"
    err, text = run("git", "log", "--oneline", "-1")
    check("a check runs in the head worktree: git log works there (positive control)", not err and exit_of(text) == "exit 0" and "head" in text, text)
    err, text = run("sh", "-c", "pwd")
    check("its working directory is the head worktree", f"\n{evidence}\n" in text, text)
    for label, path in (("~/.config/agent-fabric/secrets.env", secret_file), ("a file under ~/.ssh", ssh_file)):
        check(f"control: {label} exists and is readable outside the sandbox", "PLANTED" in open(path, encoding="utf-8").read())
        err, text = run("cat", path)
        check(f"reading {label} from inside fails and shows nothing", exit_of(text) != "exit 0" and "PLANTED" not in text, text)
    for name in (".gnupg", ".password-store"):
        os.makedirs(os.path.join(home, name), exist_ok=True)
    err, text = run("sh", "-c", f'ls -A "{home}"')
    check("the home inside holds neither the secret stores nor the keys", not any(n in text.split("---")[1] for n in (".ssh", ".config", ".gnupg", ".password-store")), text)
    err, text = run("sh", "-c", f'echo x > "{evidence}/planted"')
    check("a write to the head worktree fails and leaves nothing", exit_of(text) != "exit 0" and not os.path.exists(f"{evidence}/planted"), text)
    common = subprocess.run(["git", "-C", clone, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True,
                            timeout=30).stdout.strip()
    err, text = run("sh", "-c", f'echo x > "{common}/planted"')
    check("a write to the clone's git directory fails and leaves nothing", exit_of(text) != "exit 0" and not os.path.exists(f"{common}/planted"), text)
    err, text = run("sh", "-c", f'echo x > "{clone}/planted"')
    check("a write into the clone's own tree fails (it is not even there)", exit_of(text) != "exit 0" and not os.path.exists(f"{clone}/planted"), text)
    subprocess.run(["git", "-C", clone, "config", "remote.origin.url", "https://x-access-token:PLANTED-REMOTE-TOKEN@example.invalid/r.git"],
                   check=True, timeout=30)
    own = subprocess.run(["git", "-C", evidence, "rev-parse", "--path-format=absolute", "--git-dir"], capture_output=True, text=True,
                         timeout=30).stdout.strip()
    # Each of these holds a marker outside the sandbox (the controls) and must not exist inside, while git log still works (the first case).
    for rel in ("config.worktree", "hooks/planted-hook", "logs/planted-log", "info/planted-info", "worktrees/other/config.worktree"):
        os.makedirs(os.path.dirname(os.path.join(common, rel)), exist_ok=True)
        with open(os.path.join(common, rel), "w", encoding="utf-8") as fh:
            fh.write("PLANTED-GITDIR\n")
    with open(os.path.join(own, "config.worktree"), "w", encoding="utf-8") as fh:
        fh.write("PLANTED-GITDIR\n")
    for rel in ("config.worktree", "hooks/planted-hook", "logs/planted-log", "info/planted-info", "worktrees/other/config.worktree"):
        check(f"control: {rel} of the clone is readable outside the sandbox", "PLANTED-GITDIR" in open(os.path.join(common, rel), encoding="utf-8").read())
    check("control: the clone's config holds the remote credential outside the sandbox", "PLANTED-REMOTE-TOKEN" in open(os.path.join(common, "config"), encoding="utf-8").read())
    for label, path in (("the config", f"{common}/config"), ("config.worktree", f"{common}/config.worktree"),
                        ("the worktree's own config.worktree", f"{own}/config.worktree"), ("hooks/", f"{common}/hooks/planted-hook"),
                        ("logs/", f"{common}/logs/planted-log"), ("info/", f"{common}/info/planted-info"),
                        ("another worktree's directory", f"{common}/worktrees/other/config.worktree")):
        err, text = run("cat", path)
        check(f"{label} of the clone cannot be read from inside", exit_of(text) != "exit 0" and "PLANTED" not in text, text)
    err, text = run("git", "rev-list", "--count", "HEAD")
    check("git still reads history there: rev-list over the objects and refs", exit_of(text) == "exit 0" and text.split("\n")[2].strip().isdigit(), text)
    err, text = run("git", "show", "--stat", "--format=%s", "HEAD")
    check("and git show of the head works", exit_of(text) == "exit 0" and "head" in text, text)
    err, text = run("env")
    check("control: the process holds a secret", bool(os.environ.get("FABRIC_TEST_API_TOKEN")))
    check("a secret of the process is not in a check's environment", "hostile-secret-value" not in text and "FABRIC_TEST_API_TOKEN" not in text
          and "CLAUDE_PROJECT_DIR" not in text, text)
    err, text = run("sh", "-c", "echo hello > /tmp/scratch && cat /tmp/scratch && touch /tmp/second")
    check("/tmp is writable inside", exit_of(text) == "exit 0" and "hello" in text, text)
    err, text = run("sh", "-c", "test ! -e /tmp/scratch && test ! -e /tmp/second && echo clean")
    check("what a check wrote to /tmp is gone for the next one", exit_of(text) == "exit 0" and "clean" in text, text)
    check("and was never on the host's /tmp", not os.path.exists("/tmp/scratch") and not os.path.exists("/tmp/second"))
    err, text = run("sh", "-c", 'echo "$TMPDIR"')
    check("TMPDIR is /tmp inside", "\n/tmp\n" in text, text)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    connect = "import socket,sys\ntry:\n socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)\nexcept OSError as e:\n print('errno', e.errno); sys.exit(3)\nprint('connected')"
    outside = subprocess.run([py, "-c", connect, "127.0.0.1", str(port)], capture_output=True, text=True, timeout=30)
    check("control: outside the sandbox the same connect to 127.0.0.1 succeeds", outside.returncode == 0 and "connected" in outside.stdout, outside.stdout + outside.stderr)
    err, text = run(py, "-c", connect, "127.0.0.1", str(port))
    check("a connect to 127.0.0.1 from inside fails", exit_of(text) == "exit 3" and "connected" not in text, text)
    err, text = run(py, "-c", connect, "93.184.216.34", "443")
    check("a connect to a public address from inside fails", exit_of(text) == "exit 3" and "connected" not in text, text)
    listener.close()
    t0 = time.monotonic()
    err, text = run("sh", "-c", f"sleep 4713.{TAG} & sleep 4713.{TAG}", timeout_s=1)
    time.sleep(0.3)
    check("a check that forks and sleeps is ended at its budget, the group with it", exit_of(text).startswith("ended at the budget")
          and time.monotonic() - t0 < 15 and not processes_with(f"4713.{TAG}"), text)
    err, text = run("yes")
    check("a check that floods is cut and says so", "output cut" in exit_of(text) and "output cut at" in text, text[:300])
    err, text = run("sh", "-c", "exit 5")
    check("control: a check's own exit status is reported", exit_of(text) == "exit 5", text)

    print("-- review_check: what is not proved runs nothing")
    done = os.path.join(scratch, "ran-anyway")
    probe_cmd = ["sh", "-c", f'touch "{done}"']

    def with_path(directory: str):
        old = os.environ["PATH"]
        os.environ["PATH"] = directory
        try:
            return fresh("review_check", head=head, argv=probe_cmd)
        finally:
            os.environ["PATH"] = old
    empty = os.path.join(scratch, "empty-bin")
    os.makedirs(empty)
    os.symlink("/usr/bin/git", os.path.join(empty, "git"))
    err, text = with_path(empty)
    check("bwrap absent from PATH: nothing runs, one line says why", err and "not installed" in text and "\n" not in text and not os.path.exists(done), text)
    nothing = os.path.join(scratch, "bin-nothing")
    os.makedirs(nothing)
    with open(os.path.join(nothing, "bwrap"), "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")           # starts, exits 0, runs nothing: proves nothing
    os.chmod(os.path.join(nothing, "bwrap"), 0o755)
    err, text = with_path(nothing + ":/usr/bin")
    check("a sandbox that runs nothing is not proved and nothing runs", err and "ran nothing it was asked" in text and not os.path.exists(done), text)
    bare = os.path.join(scratch, "bin-bare")
    os.makedirs(bare)
    with open(os.path.join(bare, "bwrap"), "w") as fh:
        fh.write('#!/bin/sh\nwhile [ "$1" != "--" ]; do shift; done\nshift\nexec "$@"\n')      # runs the command with no sandbox at all
    os.chmod(os.path.join(bare, "bwrap"), 0o755)
    err, text = with_path(bare + ":/usr/bin")
    leftover = [n for n in os.listdir(evidence) if n.startswith(".fabric-write-probe-")]
    check("a sandbox that lets the probe write is not proved: nothing runs, and the probe file is not left",
          err and "cannot refuse a write" in text and not os.path.exists(done) and not leftover, text + str(leftover))
    err, text = run("true")
    check("control: with the real bwrap back on PATH the proof passes and the check runs", exit_of(text) == "exit 0", text)
    err, text = call("review_check", head=base, argv=["true"])
    check("a head with no checkout is refused, nothing runs", err and "no checkout" in text, text)
    where = review_brief.evidence_path(review_brief.repo_name_of(clone), base)
    os.makedirs(where)
    err, text = call("review_check", head=base, argv=["true"])
    check("a directory at the evidence path that is no worktree of the clone is refused", err and "not a worktree of this clone" in text, text)
    os.rmdir(where)
    subprocess.run(["git", "-C", clone, "worktree", "add", "-q", "--detach", where, head], check=True, capture_output=True, timeout=60)
    err, text = call("review_check", head=base, argv=["true"])
    check("a worktree of the clone at another commit than the head asked for is refused", err and "is not the worktree of" in text, text)
    subprocess.run(["git", "-C", clone, "worktree", "remove", "--force", where], check=True, capture_output=True, timeout=60)
    foreign = os.path.join(scratch, "foreign")
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", clone, foreign], check=True, capture_output=True, timeout=60)
    subprocess.run(["git", "-C", foreign, "worktree", "add", "-q", "--detach", where, base], check=True, capture_output=True, timeout=60)
    err, text = call("review_check", head=base, argv=["true"])
    check("a worktree at the right commit that belongs to another repository is refused", err and "is not the worktree of" in text, text)
    keep = srv.Server()
    check("control: one server proves the real bwrap and runs a check", not keep.call("review_check", {"head": head, "argv": ["true"]})["isError"])
    old_path = os.environ["PATH"]
    os.environ["PATH"] = bare + ":/usr/bin"
    try:
        r = keep.call("review_check", {"head": head, "argv": probe_cmd})
    finally:
        os.environ["PATH"] = old_path
    check("a proof of one bwrap is not a proof of another: the same server, a different binary, is proved again and refused",
          r["isError"] and "cannot refuse a write" in r["content"][0]["text"] and not os.path.exists(done), r["content"][0]["text"])


if __name__ == "__main__":
    sys.exit(main())
