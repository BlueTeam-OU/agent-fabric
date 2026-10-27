#!/usr/bin/env python3
"""fabric-jobs tidy (j90): the build output of the checkouts under ~/projects that no open job holds. Run in process (jobs.main) with
a scratch HOME holding real git repositories and a hand-written job list; every keep rule has its positive control (the same
tree, the rule lifted, goes)."""
from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:700]}"))
        fails += not good

    # Outside any home: cargo reads a configuration in every parent of a target, and the fleet's TMPDIR is under the login's home.
    with tempfile.TemporaryDirectory(prefix="jobs-tidy-", dir="/tmp") as raw:
        tmp = os.path.realpath(raw)
        home = os.path.join(tmp, "home")
        projects = os.path.join(home, "projects")
        os.makedirs(projects)
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        state = os.path.join(tmp, "state")
        os.environ.pop("CARGO_HOME", None)
        os.environ.update(HOME=home, AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=state, AGENT_FABRIC_SECRET_STORE=store)
        spec = importlib.util.spec_from_file_location("jobs_under_test", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
        jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs)
        login = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        jobs_file = os.path.join(state, "agents", login, "jobs.json")
        os.makedirs(os.path.dirname(jobs_file))
        lt = sys.modules["fabric_jobs"].leave_targets
        tidy_mod = sys.modules["fabric_jobs"].tidy

        def git(repo: str, *args: str) -> None:
            subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=git_env(), timeout=60)

        def write(path: str, size: int = 2048) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write("x" * size)

        n_trees = 0

        def tree(*built: str, ignore: str = "target\nnode_modules\n", sources: tuple[str, ...] = ("Cargo.toml", "package.json")) -> str:
            """A repository under ~/projects with its sources committed and `built` files (paths) left as ignored output."""
            nonlocal n_trees
            n_trees += 1
            path = os.path.join(projects, f"t{n_trees}")
            os.makedirs(path)
            git(path, "init", "-q", "-b", "main")
            for s in sources:
                write(os.path.join(path, s), 10)
            write(os.path.join(path, ".gitignore"), 0)
            with open(os.path.join(path, ".gitignore"), "w") as fh:
                fh.write(ignore)
            git(path, "add", "-A")
            git(path, "commit", "-q", "-m", "sources")
            for b in built:
                write(os.path.join(path, b))
            return path

        def listing(*entries: dict) -> None:
            with open(jobs_file, "w") as fh:
                json.dump({"agent": login, "host": jobs.identity.current_host(), "seq": len(entries), "jobs": list(entries)}, fh)

        def job(n: int, state_: str, **paths: str) -> dict:
            return {"id": f"j{n}", "title": "t", "state": state_, **paths}

        def tidy(*flags: str) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            os.chdir(tmp)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    rc = jobs.main(["tidy", *flags])
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
            return rc, out.getvalue(), err.getvalue()

        listing()
        print("fabric-jobs tidy: which trees")
        for st in ("active", "queued", "paused", "blocked"):
            t = tree("target/debug/a.o", "node_modules/x/index.js")
            listing(job(1, st, worktree=t, working_copy=None))
            rc, out, err = tidy()
            check(f"a {st} job's worktree keeps its target and its node_modules, said", rc == 0 and os.path.isdir(os.path.join(t, "target")) and os.path.isdir(os.path.join(t, "node_modules"))
                  and f"kept {t}: it is, holds or lies in a checkout of open job j1" in out, out + err)
            listing()
            tidy()
        t = tree("target/debug/a.o")
        listing(job(1, "active", worktree=None, working_copy=t))
        rc, out, err = tidy()
        check("an open job's working copy is left alone as well", rc == 0 and os.path.isdir(os.path.join(t, "target")), out + err)
        listing(job(1, "active", worktree=os.path.join(projects, "nowhere"), working_copy=os.path.dirname(t)))
        rc, out, err = tidy()
        check("…and so is a tree below a path an open job holds", rc == 0 and os.path.isdir(os.path.join(t, "target")), out + err)

        t_done, t_drop, t_deliv, t_free = (tree("target/debug/a.o") for _ in range(4))
        t_ok = tree("target/debug/a.o")
        listing(job(1, "done", worktree=t_done), job(2, "dropped", worktree=t_drop), job(3, "delivered", worktree=t_deliv), job(4, "active", worktree=t_ok))
        rc, out, err = tidy()
        check("a done, a dropped, a delivered job's and an unrecorded tree's targets go; the open job's stays",
              rc == 0 and not any(os.path.exists(os.path.join(x, "target")) for x in (t_done, t_drop, t_deliv, t_free)) and os.path.isdir(os.path.join(t_ok, "target"))
              and all(f"removed {x}/target (" in out for x in (t_done, t_drop, t_deliv, t_free)), out + err)
        listing()

        print("fabric-jobs tidy: what goes")
        t = tree("target/debug/a.o", "node_modules/x/index.js", "app/target/b", "app/Cargo.toml", "docs/target/c", "ui/node_modules/y", "ui/package.json",
                 "w/x/y/Cargo.toml", "w/x/y/target/z", "w/x/y/z/Cargo.toml", "w/x/y/z/target/z")
        rc, out, err = tidy()
        gone = [p for p in ("target", "node_modules", "app/target", "ui/node_modules", "w/x/y/target") if not os.path.exists(os.path.join(t, p))]
        check("a target beside a Cargo.toml and a node_modules beside a package.json go, at the top and below",
              rc == 0 and gone == ["target", "node_modules", "app/target", "ui/node_modules", "w/x/y/target"] and f"removed {t}/node_modules (" in out and f"removed {t}/ui/node_modules (" in out, out + err)
        check("…one beside no marker, and one deeper than 4 levels, stay; so do the sources",
              os.path.isdir(os.path.join(t, "docs", "target")) and os.path.isdir(os.path.join(t, "w/x/y/z/target")) and os.path.isfile(os.path.join(t, "Cargo.toml")) and os.path.isfile(os.path.join(t, "package.json")), out)
        m = re.search(r"^freed: (\d+(\.\d)? \w+)$", out, re.M)
        check("a total closes the run", bool(m) and out.rstrip().splitlines()[-1].startswith("freed: "), out)
        t = tree("node_modules/x/package.json", "node_modules/x/node_modules/y/i.js")
        rc, out, err = tidy()
        check("a node_modules is removed whole, not entered: one line, no warning for the one inside it",
              rc == 0 and not os.path.exists(os.path.join(t, "node_modules")) and out.count(f"{t}/") == 1 and "warning" not in out, out + err)
        t = tree()
        with open(os.path.join(t, "target.bin"), "wb") as fh:
            fh.write(b"\0" * (3 << 20))
        os.makedirs(os.path.join(t, "target"))
        os.rename(os.path.join(t, "target.bin"), os.path.join(t, "target", "big"))
        rc, out, err = tidy()
        check("the total is the sum of what was removed", rc == 0 and f"removed {t}/target (3.0 MB)" in out and out.rstrip().endswith("freed: 3.0 MB"), out + err)
        t = tree("node_modules/x/index.js", sources=("Cargo.toml",))
        rc, out, err = tidy()
        check("a node_modules beside no package.json stays (the positive control: with one it went above)", rc == 0 and os.path.isdir(os.path.join(t, "node_modules")), out + err)
        sub = os.path.join(projects, "plain")
        write(os.path.join(sub, "Cargo.toml"), 5)
        write(os.path.join(sub, "target", "x"))
        rc, out, err = tidy()
        check("a directory under ~/projects that is no checkout is not a tree", rc == 0 and os.path.isdir(os.path.join(sub, "target")) and "plain" not in out, out + err)

        print("fabric-jobs tidy: dry run")
        t = tree("target/debug/a.o", "node_modules/x/index.js")
        rc, out, err = tidy("--dry-run")
        check("--dry-run removes nothing and says what would go and what it would free", rc == 0 and os.path.isdir(os.path.join(t, "target")) and os.path.isdir(os.path.join(t, "node_modules"))
              and f"would remove {t}/target (" in out and re.search(r"^would free: \d", out, re.M) and "removed" not in out.replace("would remove", ""), out + err)
        rc, out, err = tidy()
        check("…and the run after it removes them", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)

        print("fabric-jobs tidy: what is kept")
        t = tree("target/debug/a.o")
        standing = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=os.path.join(t, "target", "debug"))
        try:
            rc, out, err = tidy()
            held = os.path.isdir(os.path.join(t, "target", "debug"))
        finally:
            standing.kill()
            standing.wait()
        check("a target a process of this uid stands in is kept, said", rc == 0 and held and f"kept {t}/target: a process of this uid stands in it" in out, out + err)
        t2 = tree("node_modules/x/i.js")
        standing = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=os.path.join(t2, "node_modules", "x"))
        try:
            rc, out, err = tidy()
            held = os.path.isdir(os.path.join(t2, "node_modules", "x"))
        finally:
            standing.kill()
            standing.wait()
        check("…a node_modules too", rc == 0 and held and f"kept {t2}/node_modules: a process of this uid stands in it" in out, out + err)
        rc, out, err = tidy()
        check("…the process gone, both go", rc == 0 and not os.path.exists(os.path.join(t, "target")) and not os.path.exists(os.path.join(t2, "node_modules")), out + err)

        t = tree("target/debug/a.o", "target/debug/.cargo-lock")
        fd = os.open(os.path.join(t, "target", "debug", ".cargo-lock"), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            rc, out, err = tidy()
            kept = os.path.exists(os.path.join(t, "target", "debug", "a.o"))
        finally:
            os.close(fd)
        check("a target whose .cargo-lock is held is kept, a build is running", rc == 0 and kept and f"kept {t}/target: its .cargo-lock is held" in out, out + err)
        rc, out, err = tidy()
        check("…released, it goes", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)

        t = tree("target/debug/a.o", ".cargo/config.toml")
        with open(os.path.join(t, ".cargo", "config.toml"), "w") as fh:
            fh.write('[build]\ntarget-dir = "../../elsewhere"\n')
        rc, out, err = tidy()
        check("a cargo configuration sending the target directory elsewhere keeps the target, says where",
              rc == 0 and os.path.isdir(os.path.join(t, "target")) and f"kept {t}/target: a cargo configuration sends the target directory to {os.path.join(home, 'elsewhere')}" in out, out + err)
        os.unlink(os.path.join(t, ".cargo", "config.toml"))
        write(os.path.join(t, ".cargo", "config.toml"), 0)
        rc, out, err = tidy()
        check("…an empty configuration does not: the target goes", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)

        t = tree(sources=("Cargo.toml",))
        write(os.path.join(tmp, "real", "keep.o"))
        os.symlink(os.path.join(tmp, "real"), os.path.join(t, "target"))
        rc, out, err = tidy()
        check("a target that is a link is not followed or removed", rc == 0 and os.path.exists(os.path.join(tmp, "real", "keep.o")) and os.path.islink(os.path.join(t, "target")) and f"kept {t}/target: a link" in out, out + err)
        real_tree = tree("target/debug/a.o")
        os.symlink(real_tree, os.path.join(projects, "linked-tree"))
        os.rename(os.path.join(real_tree, "target"), os.path.join(tmp, "moved-target"))
        rc, out, err = tidy()
        check("a tree that is a link is kept, said", rc == 0 and f"kept {os.path.join(projects, 'linked-tree')}: a link" in out, out + err)
        os.unlink(os.path.join(projects, "linked-tree"))

        t = tree("node_modules/x/i.js")
        git(t, "add", "-f", "node_modules/x/i.js")
        git(t, "commit", "-q", "-m", "vendored")
        rc, out, err = tidy()
        check("a directory with a tracked file under it is kept, whole", rc == 0 and os.path.isfile(os.path.join(t, "node_modules", "x", "i.js")) and f"kept {t}/node_modules: git tracks files under it" in out, out + err)
        t = tree("target/debug/a.o")
        git(t, "add", "-f", "target/debug/a.o")
        git(t, "commit", "-q", "-m", "oops")
        rc, out, err = tidy()
        check("…a target as well", rc == 0 and os.path.isfile(os.path.join(t, "target", "debug", "a.o")) and f"kept {t}/target: git tracks files under it" in out, out + err)

        t = tree("target/debug/a.o")
        os.rename(os.path.join(t, ".git"), os.path.join(t, ".gitx"))
        write(os.path.join(t, ".git"), 3)
        rc, out, err = tidy()
        check("a tree git cannot read is kept: unknown is not 'untracked'", rc == 0 and os.path.isdir(os.path.join(t, "target")) and f"kept {t}/target: git cannot be asked" in out, out + err)
        os.unlink(os.path.join(t, ".git"))
        os.rename(os.path.join(t, ".gitx"), os.path.join(t, ".git"))
        rc, out, err = tidy()
        check("…the repository whole again, it goes", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)

        t = tree("target/debug/a.o")
        real_lstat = os.lstat

        def foreign(name: str):
            """lstat that shows another uid owning the path called `name` and nothing else."""
            def lstat(path, *a, **kw):
                st = real_lstat(path, *a, **kw)
                if os.path.basename(str(path)) != name:
                    return st
                return types.SimpleNamespace(**{**{k: getattr(st, k) for k in dir(st) if k.startswith("st_")}, "st_uid": st.st_uid + 1})
            return lstat
        os.symlink(os.path.join(t, "target"), os.path.join(t, "target", "debug", "lnk"))      # a link to a directory
        for owned, what in (("a.o", "a file"), ("debug", "a directory"), ("lnk", "a link to a directory"), ("target", "the target itself")):
            os.lstat = foreign(owned)
            try:
                said = lt.judge(os.path.join(t, "target"), t, real_lstat(t).st_dev, [], "")
            finally:
                os.lstat = real_lstat
            check(f"{what} in a target that another uid owns keeps the whole target (the directories around it are ours)",
                  said == (f"kept {t}/target: another account owns files in it", 0) and os.path.isfile(os.path.join(t, "target", "debug", "a.o")), said)
        os.unlink(os.path.join(t, "target", "debug", "lnk"))
        check("…positive control: the same target judged as its owner would go", lt.judge(os.path.join(t, "target"), t, os.lstat(t).st_dev, [], "", True)[0].startswith("would remove "))
        real_uid = os.getuid
        os.getuid = lambda: real_uid() + 1
        try:
            lines, freed = tidy_mod.tidy_tree(t, os.stat(projects).st_dev, {}, [], "", False)
        finally:
            os.getuid = real_uid
        check("a tree another account owns is kept", freed == 0 and lines == [f"kept {t}: owned by another account"] and os.path.isdir(os.path.join(t, "target")), lines)
        lines, freed = tidy_mod.tidy_tree(t, os.stat(projects).st_dev + 1, {}, [], "", False)
        check("a tree on another filesystem than ~/projects is kept", freed == 0 and lines == [f"kept {t}: on another filesystem"] and os.path.isdir(os.path.join(t, "target")), lines)
        check("a target on another filesystem than its tree's is kept whole", lt.judge(os.path.join(t, "target"), t, -1, [], "") == (f"kept {os.path.join(t, 'target')}: another filesystem", 0))
        real_cwds = lt.live_cwds

        def blind() -> list[str]:
            raise lt.Unknown("processes cannot be listed")
        lt.live_cwds = blind
        try:
            rc, out, err = tidy()
        finally:
            lt.live_cwds = real_cwds
        check("a process list that cannot be read keeps everything", rc == 0 and os.path.isdir(os.path.join(t, "target")) and "kept" in out and "cannot be listed" in out, out + err)
        rc, out, err = tidy()
        check("…readable again, it goes", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)

        print("fabric-jobs tidy: what is refused")
        t = tree("target/debug/a.o")
        with open(jobs_file, "w") as fh:
            fh.write("{ not json")
        rc, out, err = tidy()
        check("a job list that cannot be read removes nothing and says so, exit 1", rc == 1 and os.path.isdir(os.path.join(t, "target")) and "job list cannot be read" in err and "nothing was removed" in err, out + err)
        listing("not a job")
        rc, out, err = tidy()
        check("a list entry that is no job is the same", rc == 1 and os.path.isdir(os.path.join(t, "target")) and "not a job" in err and "nothing was removed" in err, out + err)
        listing(job(1, "somethingelse", worktree=os.path.join(projects, "nowhere")))
        rc, out, err = tidy()
        check("a job with a state the tool does not know is the same: unknown is not closed", rc == 1 and os.path.isdir(os.path.join(t, "target")) and "state" in err and "nothing was removed" in err, out + err)
        listing(job(1, "active", worktree=7))
        rc, out, err = tidy()
        check("a job whose worktree is not a path is the same", rc == 1 and os.path.isdir(os.path.join(t, "target")) and "nothing was removed" in err, out + err)
        listing(job(1, "done", worktree=7))
        rc, out, err = tidy()
        check("…positive control: a closed job's field is not read, the run goes through", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)
        t = tree("target/debug/a.o")
        listing()
        os.chmod(projects, 0)
        try:
            rc, out, err = tidy()
        finally:
            os.chmod(projects, 0o755)
        check("an unreadable ~/projects removes nothing and says so, exit 1", rc == 1 and os.path.isdir(os.path.join(t, "target")) and "cannot be read" in err, out + err)
        rc, out, err = tidy()
        check("…readable again, it goes", rc == 0 and not os.path.exists(os.path.join(t, "target")), out + err)
        os.rename(projects, projects + "-away")
        rc, out, err = tidy()
        check("no ~/projects at all is a fact, not a failure: exit 0, nothing to tidy", rc == 0 and "nothing to tidy" in out, out + err)
        os.rename(projects + "-away", projects)

    print(f"{'FAILED' if fails else 'all ok'}: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
