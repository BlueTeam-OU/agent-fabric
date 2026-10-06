#!/usr/bin/env python3
"""bin/fabric-fresh where git cannot say whether the working copy is clean.

A job is not done while its tree has uncommitted changes, and a tree git
cannot answer for is not known to be clean: exit 3, said, before anything
is stopped; --force still goes ahead. A file name that is not UTF-8 is a
change like any other. The cases stop before the walk up to the session
(test_fabric_fresh_cli.py covers that), so a run that gets past the check
ends at "no <comm> process above", exit 2. Plain script: prints ok/FAIL,
exit 1 on any failure."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.join(ROOT, "bin", "fabric-fresh")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        wc, bin_, state = os.path.join(t, "wc"), os.path.join(t, "bin"), os.path.join(t, "state")
        for d in (wc, bin_, state):
            os.makedirs(d)
        killed = os.path.join(t, "killed")
        with open(os.path.join(bin_, "record-kill"), "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\necho "$*" > "{killed}"\n')
        os.chmod(os.path.join(bin_, "record-kill"), 0o755)
        # A git that knows it is in a working copy and cannot read its index.
        real_git = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        broken = os.path.join(t, "broken")
        os.makedirs(broken)
        with open(os.path.join(broken, "git"), "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\ncase "$1" in\n  rev-parse) echo true ;;\n'
                     '  status) echo "fatal: index file corrupt" >&2; exit 128 ;;\n'
                     f'  *) exec "{real_git}" "$@" ;;\nesac\n')
        os.chmod(os.path.join(broken, "git"), 0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env.update(AGENT_FABRIC_LAUNCH_PROFILE="p", AGENT_FABRIC_LAUNCH_OPENING="1", AGENT_FABRIC_STATE_DIR=state,
                   AGENT_FABRIC_FRESH_KILL=os.path.join(bin_, "record-kill"),
                   AGENT_FABRIC_FRESH_COMM="no-such-proc")

        def fresh(*args: str, path: str | None = None) -> tuple[int, str]:
            e = dict(env)
            if path:
                e["PATH"] = path + os.pathsep + e.get("PATH", "")
            r = subprocess.run([CMD, *args], env=e, cwd=wc, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=120)
            return r.returncode, r.stdout

        subprocess.run(["git", "-C", wc, "init", "-q"], check=True, timeout=30)

        print("fabric-fresh: a working copy git cannot answer for is not clean")
        rc, out = fresh(path=broken)
        check("a failing git status: exit 3, the reason said, nothing stopped",
              rc == 3 and "cannot tell whether" in out and "index file corrupt" in out
              and not os.path.exists(killed), f"rc={rc}\n{out}")
        rc, out = fresh("--force", path=broken)
        check("…--force goes ahead past it", rc == 2 and "no no-such-proc process" in out, f"rc={rc}\n{out}")

        print("fabric-fresh: no working copy is no refusal")
        for where in ("bare", "dot-git"):
            d = os.path.join(t, where)
            if where == "bare":
                subprocess.run(["git", "init", "-q", "--bare", d], check=True, timeout=30)
            else:
                d = os.path.join(wc, ".git")
            r = subprocess.run([CMD], env=env, cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               timeout=120)
            check(f"{where}: past the check, to the walk", r.returncode == 2 and "no no-such-proc process" in r.stdout,
                  f"rc={r.returncode}\n{r.stdout}")

        print("fabric-fresh: a repository git refuses to read is not clean")
        # Dubious ownership (a repository another account owns): rev-parse
        # fails, as it does outside a repository, but with another reason.
        dubious = os.path.join(t, "dubious")
        os.makedirs(dubious)
        with open(os.path.join(dubious, "git"), "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\necho "fatal: detected dubious ownership in repository at \'/x\'" >&2\nexit 128\n')
        os.chmod(os.path.join(dubious, "git"), 0o755)
        rc, out = fresh(path=dubious)
        check("dubious ownership: exit 3, the reason said, nothing stopped",
              rc == 3 and "dubious ownership" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        rc, out = fresh("--force", path=dubious)
        check("…--force goes ahead past it", rc == 2 and "no no-such-proc process" in out, f"rc={rc}\n{out}")
        plain = os.path.join(t, "plain")
        os.makedirs(plain)
        # A translated locale is asked for too; it proves LC_ALL=C only on a
        # host that has a German locale generated (git falls back to
        # English without one, as on the fabric's hosts today).
        r = subprocess.run([CMD], env={**env, "LANGUAGE": "de", "LANG": "de_DE.UTF-8"}, cwd=plain,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        check("a directory that is no repository is no working copy, not a refusal",
              r.returncode == 2 and "no no-such-proc process" in r.stdout, f"rc={r.returncode}\n{r.stdout}")

        # No git on the host at all: no working copy, as the bash read
        # `command not found`; the shim needs bash, dirname and readlink,
        # and nothing else is on PATH.
        nogit = os.path.join(t, "nogit")
        os.makedirs(nogit)
        for tool in ("bash", "dirname", "readlink"):
            os.symlink(shutil.which(tool), os.path.join(nogit, tool))
        r = subprocess.run([CMD], env={**env, "PATH": nogit}, cwd=wc, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=120)
        check("no git at all: no working copy, past the check", r.returncode == 2
              and "no no-such-proc process" in r.stdout, f"rc={r.returncode}\n{r.stdout}")

        print("fabric-fresh: a file name that is not UTF-8 is a change")
        subprocess.run(["git", "-C", wc, "config", "core.quotePath", "false"], check=True, timeout=30)
        with open(os.path.join(os.fsencode(wc), b"caf\xe9"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        rc, out = fresh()
        check("exit 3, uncommitted changes", rc == 3 and "uncommitted changes" in out, f"rc={rc}\n{out}")

        print("fabric-fresh: git that does not answer is not a clean tree")
        spec = importlib.util.spec_from_file_location("fabric_fresh", os.path.join(ROOT, "tools", "fabric", "fresh.py"))
        fresh_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh_mod)  # type: ignore[union-attr]
        slow = os.path.join(t, "slow")
        os.makedirs(slow)
        with open(os.path.join(slow, "git"), "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\ncase "$1" in\n  rev-parse) echo true ;;\n  status) exec sleep 30 ;;\nesac\n')
        os.chmod(os.path.join(slow, "git"), 0o755)
        fresh_mod.TIMEOUT_S = 1
        saved = os.environ["PATH"]
        os.environ["PATH"] = slow + os.pathsep + saved
        try:
            fresh_mod.dirty_toplevel()
            raised = ""
        except fresh_mod.Unknown as e:
            raised = str(e)
        finally:
            os.environ["PATH"] = saved
        check("a git status past the bound is Unknown, named", "git status did not answer" in raised, raised)

    print(f"\ntest_fabric_fresh_git: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
