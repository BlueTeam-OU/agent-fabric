#!/usr/bin/env python3
"""bin/fabric-branches: the report deletes nothing; the sweep deletes
exactly what is wholly on origin/main, keeps the rest, and never touches
a remote branch. Ported from tests/test_fabric-branches.sh (ADR-040
Wave 6), case for case. Plain script: prints ok/FAIL, exit 1 on any
failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.abspath(os.environ.get("FABRIC_BRANCHES") or os.path.join(ROOT, "bin", "fabric-branches"))
if not os.path.isfile(CMD):
    sys.exit(f"test: script under test not found at {CMD}")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    me = f"{host}/{LOGIN}"

    with tempfile.TemporaryDirectory() as t:
        origin, wc = f"{t}/origin.git", f"{t}/wc"
        heads = f"{t}/gh-heads"
        os.makedirs(f"{t}/bin")
        # No network: a gh that answers "no pull request" for every branch,
        # records the head it was asked about, and knows one pull request.
        gh = f"{t}/bin/gh"
        with open(gh, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\n"
                     'head=""\n'
                     'while [ $# -gt 0 ]; do\n'
                     f'    case "$1" in --head) head="$2"; echo "$2" >> "{heads}" ;; esac\n'
                     '    shift\n'
                     'done\n'
                     f'if [ "$head" = "{me}/owed-remote" ]; then echo \'[{{"number":7,"state":"OPEN"}}]\'; else echo \'[]\'; fi\n'
                     'exit 0\n')
        os.chmod(gh, 0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        # The scratch origin is a local path: GH_REPO names the repository the
        # fake gh serves, since gh's default is never used (gh.this_repo).
        env.update(PATH=f"{t}/bin{os.pathsep}{env.get('PATH', '')}", AGENT_FABRIC_STATE_DIR=f"{t}/state",
                   GH_REPO="o/r")

        def git(*args: str, cwd: str = wc, ok: bool = False) -> str:
            r = subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t",
                                "-c", "commit.gpgsign=false", *args], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=60)
            if r.returncode and not ok:
                raise RuntimeError(f"git {' '.join(args)}: exit {r.returncode}")
            return r.stdout

        def has_branch(name: str, cwd: str = wc) -> bool:
            return bool(git("branch", "--list", name, cwd=cwd).strip())

        def run(*args: str, cwd: str = wc) -> tuple[int, str]:
            r = subprocess.run([CMD, *args], cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=120)
            return r.returncode, r.stdout

        def asked() -> list[str]:
            try:
                with open(heads, encoding="utf-8") as fh:
                    return fh.read().splitlines()
            except OSError:
                return []

        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], env=env, check=True, timeout=30)
        subprocess.run(["git", "clone", "-q", origin, wc], env=env, check=True, timeout=30,
                       stderr=subprocess.DEVNULL)
        git("commit", "-q", "--allow-empty", "-m", "base")
        git("push", "-q", "origin", "HEAD:main")
        # A clone of an empty origin has no origin/HEAD, and before git 2.48
        # no fetch sets it: set it as a clone of a non-empty one has it.
        git("remote", "set-head", "origin", "main")
        # merged: its commit is on main. owed: one commit that is not.
        # theirs: a local copy of another agent's branch, merged.
        git("checkout", "-q", "-b", f"{me}/merged")
        git("commit", "-q", "--allow-empty", "-m", "merged")
        git("push", "-q", "origin", f"{me}/merged", f"{me}/merged:main")
        git("branch", "-q", "-u", f"origin/{me}/merged")
        git("checkout", "-q", "-b", f"{me}/owed")
        git("commit", "-q", "--allow-empty", "-m", "owed")
        git("push", "-q", "-u", "origin", f"{me}/owed:{me}/owed-remote")
        git("checkout", "-q", "main")
        git("pull", "-q", "--ff-only", "origin", "main")
        git("push", "-q", "origin", "main:other-host/other-login/fix")
        git("fetch", "-q", "origin")
        git("branch", "-q", "theirs", "origin/other-host/other-login/fix")
        git("worktree", "add", "-q", f"{t}/wt-clean", "-b", "wt-clean", "main")
        git("worktree", "add", "-q", f"{t}/wt-dirty", "-b", "wt-dirty", "main")
        with open(f"{t}/wt-dirty/new", "w", encoding="utf-8") as fh:
            fh.write("x\n")
        # Clean and at 0, each kept for its own reason: locked (in use),
        # holding an ignored file (removal would delete it), and the one a
        # sweep runs in.
        git("worktree", "add", "-q", f"{t}/wt-locked", "-b", "wt-locked", "main")
        git("worktree", "lock", f"{t}/wt-locked")
        git("worktree", "add", "-q", f"{t}/wt-ignored", "-b", "wt-ignored", "main")
        with open(f"{wc}/.git/info/exclude", "a", encoding="utf-8") as fh:
            fh.write(".env\n")
        with open(f"{t}/wt-ignored/.env", "w", encoding="utf-8") as fh:
            fh.write("secret\n")
        git("worktree", "add", "-q", f"{t}/wt-here", "-b", "wt-here", "main")

        print("fabric-branches: the report")
        rc, out = run()
        check("exit 0", rc == 0, f"rc={rc}\n{out}")
        check("…counts each branch against origin/main",
              re.search(rf"^  0 +{re.escape(me)}/merged ", out, re.M) is not None
              and re.search(rf"^  1 +{re.escape(me)}/owed ", out, re.M) is not None, out)
        check("…names a copy of another agent's branch",
              "theirs  upstream=origin/other-host/other-login/fix  (tracks another agent's branch" in out, out)
        check("…lists the commits off main", re.search(r"      [0-9a-f]* owed", out) is not None, out)
        check("…and the pull request of the remote branch it tracks, under another name",
              f"{me}/owed — pull request: #7 OPEN" in out, out)
        check("…asked by the remote name, never the local one",
              f"{me}/owed-remote" in asked() and f"{me}/owed" not in asked(), "\n".join(asked()))
        check("…and a worktree's changes", "wt-dirty  1 uncommitted change(s)" in out, out)
        check("…and deletes nothing", has_branch(f"{me}/merged") and os.path.isdir(f"{t}/wt-clean"))

        # The remote branch is deleted (a merged PR) and pruned: the
        # configured upstream still names it.
        git("branch", "-q", "-D", f"{me}/owed-remote", cwd=origin)
        git("fetch", "-q", "--prune", "origin")
        open(heads, "w").close()
        run()
        check("…even after its remote branch was deleted and pruned", f"{me}/owed-remote" in asked(),
              "\n".join(asked()))

        print("fabric-branches: refusals")
        with open(f"{wc}/dirt", "w", encoding="utf-8") as fh:
            fh.write("dirt\n")
        rc, out = run("--sweep")
        check("a dirty tree: exit 2, nothing deleted",
              rc == 2 and has_branch(f"{me}/merged") and "uncommitted changes" in out, f"rc={rc}\n{out}")
        os.remove(f"{wc}/dirt")
        git("remote", "set-url", "origin", f"{t}/nowhere.git")
        rc, out = run("--sweep")
        check("a failed fetch: exit 2, nothing deleted",
              rc == 2 and has_branch(f"{me}/merged") and "fetch origin failed" in out
              and "counting against a stale origin/main" in out, f"rc={rc}\n{out}")
        git("remote", "set-url", "origin", origin)
        rc, out = run(cwd=t)
        check("outside a working copy: exit 2", rc == 2, f"rc={rc}\n{out}")

        print("fabric-branches: a sweep from a linked worktree")
        rc, out = run("--sweep", cwd=f"{t}/wt-here")
        check("keeps the worktree it runs in",
              rc == 0 and os.path.isdir(f"{t}/wt-here") and has_branch("wt-here"), f"rc={rc}\n{out}")
        check("…and the main one", os.path.isdir(f"{wc}/.git"))
        check("…and a locked one, and one holding an ignored file",
              os.path.isdir(f"{t}/wt-locked") and os.path.isdir(f"{t}/wt-ignored")
              and os.path.isfile(f"{t}/wt-ignored/.env"), out)
        check("…each with its reason", "wt-ignored  1 ignored path(s)" in out and "wt-locked  locked" in out, out)
        check("…and their branches are kept with the reason, not refused by git",
              "KEPT wt-dirty — checked out in a worktree that stays" in out and "cannot delete branch" not in out, out)
        git("branch", "-q", "-D", f"{me}/merged", ok=True)
        git("branch", "-q", f"{me}/merged", f"origin/{me}/merged")
        if not os.path.isdir(f"{t}/wt-clean"):
            git("worktree", "add", "-q", f"{t}/wt-clean", "-b", "wt-clean2", "main", ok=True)

        print("fabric-branches: the sweep")
        rc, out = run("--sweep")
        check("exit 0", rc == 0, f"rc={rc}\n{out}")
        check("…deletes what shows 0, with its SHA",
              not has_branch(f"{me}/merged") and not has_branch("theirs")
              and re.search(rf"deleted {re.escape(me)}/merged \([0-9a-f]+\)", out) is not None, out)
        check("…keeps a branch with commits off main, and main", has_branch(f"{me}/owed") and has_branch("main"), out)
        check("…removes a clean worktree at 0, keeps one with changes",
              not os.path.isdir(f"{t}/wt-clean") and os.path.isdir(f"{t}/wt-dirty") and has_branch("wt-dirty"), out)
        check("…and no remote branch is touched",
              has_branch(f"{me}/merged", cwd=origin) and has_branch("other-host/other-login/fix", cwd=origin))
        top = git("rev-parse", "--show-toplevel").strip()
        try:
            with open(f"{t}/state/agents/{LOGIN}/branch-sweep.json", encoding="utf-8") as fh:
                recorded = top in json.load(fh)
        except (OSError, ValueError, TypeError):
            recorded = False
        check("…and the sweep is recorded for the working copy", recorded)

        print("fabric-branches: origin/HEAD missing, and the fetch sets it again")
        v = tuple(int(x) for x in re.findall(r"\d+", git("version", cwd=t))[:2])
        if v >= (2, 48):
            git("remote", "set-head", "origin", "-d")
            rc, out = run()
            check("read after the fetch (git 2.48+ sets it): counted against origin/main as before",
                  rc == 0 and "commits not on origin/main" in out, f"rc={rc}\n{out}")
        else:
            print(f"  skip git {v[0]}.{v[1]} does not set origin/HEAD on fetch")

        print("fabric-branches: a remote whose default branch is master")
        origin2, wc2 = f"{t}/herd.git", f"{t}/herd"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "master", origin2], env=env, check=True, timeout=30)
        git("clone", "-q", origin2, wc2, cwd=t)
        git("commit", "-q", "--allow-empty", "-m", "base", cwd=wc2)
        git("push", "-q", "origin", "HEAD:master", cwd=wc2)
        git("remote", "set-head", "origin", "master", cwd=wc2)
        git("checkout", "-q", "-b", "merged-here", cwd=wc2)
        git("commit", "-q", "--allow-empty", "-m", "merged", cwd=wc2)
        git("push", "-q", "origin", "merged-here:master", cwd=wc2)
        git("checkout", "-q", "master", cwd=wc2)
        git("pull", "-q", "--ff-only", "origin", "master", cwd=wc2)
        rc, out = run(cwd=wc2)
        check("origin/HEAD names master: counted against origin/master, the merged branch at 0",
              rc == 0 and "commits not on origin/master" in out and "safe to delete (0): merged-here" in out
              and "  master  " not in out, f"rc={rc}\n{out}")
        # origin/HEAD unset, and kept unset by the fetch (as before git 2.48):
        # the project's registry entry says which.
        git("remote", "set-head", "origin", "-d", cwd=wc2)
        git("config", "remote.origin.followRemoteHEAD", "never", cwd=wc2)
        fab = f"{t}/fab"
        os.makedirs(f"{fab}/projects")
        with open(f"{fab}/projects/registry.json", "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "projects": {"herd": {"remotes": [], "default_branch": "master"}}}, fh)
        with open(f"{wc2}/.agent-fabric-project", "w", encoding="utf-8") as fh:
            fh.write("herd\n")
        r = subprocess.run([CMD], cwd=wc2, env={**env, "AGENT_FABRIC_ROOT": fab}, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=120)
        check("origin/HEAD unset: the registry's default_branch, master",
              r.returncode == 0 and "commits not on origin/master" in r.stdout, f"rc={r.returncode}\n{r.stdout}")
        # A marker naming no project the registry knows, and a registry that
        # does not parse: refusals, prefixed, exit 2 — never a traceback.
        with open(f"{wc2}/.agent-fabric-project", "w", encoding="utf-8") as fh:
            fh.write("typo\n")
        r = subprocess.run([CMD], cwd=wc2, env={**env, "AGENT_FABRIC_ROOT": fab}, capture_output=True,
                           text=True, timeout=120)
        check("a marker naming an unknown project: exit 2, a prefixed refusal",
              r.returncode == 2 and r.stderr.startswith("fabric-branches: ") and "does not know" in r.stderr,
              f"rc={r.returncode}\n{r.stderr}")
        os.remove(f"{wc2}/.agent-fabric-project")
        with open(f"{fab}/projects/registry.json", "w", encoding="utf-8") as fh:
            fh.write("{")
        r = subprocess.run([CMD], cwd=wc2, env={**env, "AGENT_FABRIC_ROOT": fab}, capture_output=True,
                           text=True, timeout=120)
        check("a registry that does not parse: exit 2, a prefixed refusal, no traceback",
              r.returncode == 2 and r.stderr.startswith("fabric-branches: ") and "Traceback" not in r.stderr,
              f"rc={r.returncode}\n{r.stderr}")
        with open(f"{fab}/projects/registry.json", "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "projects": {}}, fh)
        # Neither: unknown, never guessed as main.
        r = subprocess.run([CMD], cwd=wc2, env={**env, "AGENT_FABRIC_ROOT": fab}, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=120)
        check("neither: exit 2, the default branch said unknown, nothing counted against main",
              r.returncode == 2 and "default branch" in r.stdout and "origin/main" not in r.stdout,
              f"rc={r.returncode}\n{r.stdout}")

    print(f"\ntest_fabric_branches_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
