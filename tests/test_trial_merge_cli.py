#!/usr/bin/env python3
"""runtime/github/trial-merge.sh against a throwaway origin and clone:
branches that combine and branches that conflict, the project's check
passing, failing and timing out, a run killed mid-check, two runs at once,
a ref that is not on origin, a failed fetch — and after every one of them
the caller's clone exactly as it was and no worktree left behind. Ported
from runtime/github/test_trial-merge.sh (ADR-040 Wave 6), case for case.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.abspath(os.environ.get("TRIAL_MERGE") or os.path.join(ROOT, "runtime", "github", "trial-merge.sh"))
if not os.path.isfile(UNDER_TEST):
    sys.exit(f"test: script under test not found at {UNDER_TEST}")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}

    def sentinels(argv: str) -> list[int]:
        """This login's processes whose whole command line is exactly argv:
        a sentinel a check was given, which no other process runs."""
        found = []
        for entry in os.listdir("/proc"):
            try:
                if entry.isdigit() and os.stat(f"/proc/{entry}").st_uid == os.getuid():
                    with open(f"/proc/{entry}/cmdline", "rb") as fh:
                        if fh.read().rstrip(b"\0").split(b"\0") == argv.encode().split():
                            found.append(int(entry))
            except OSError:
                pass
        return found

    def sentinel_running(argv: str) -> bool:
        return bool(sentinels(argv))

    def end_sentinel(argv: str) -> None:
        """What a regression left running, ended by pid, never by pattern."""
        for pid in sentinels(argv):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    with tempfile.TemporaryDirectory() as sandbox:
        scratch, repo, origin = f"{sandbox}/scratch", f"{sandbox}/repo", f"{sandbox}/origin.git"
        os.makedirs(scratch)

        def git(*args: str, cwd: str = repo, check_rc: bool = True) -> str:
            r = subprocess.run(["git", *args], cwd=cwd, env=base_env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=60)
            if check_rc and r.returncode:
                raise RuntimeError(f"git {' '.join(args)}: exit {r.returncode}")
            return r.stdout

        def write(path: str, text: str, mode: str = "w") -> None:
            with open(path, mode, encoding="utf-8") as fh:
                fh.write(text)

        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], env=base_env, check=True, timeout=30)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], env=base_env, check=True, timeout=30)
        for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
            git("config", k, v)
        git("remote", "add", "origin", origin)
        write(f"{repo}/f.txt", "one\ntwo\nthree\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        git("push", "-q", "origin", "main")

        def br(name: str, change) -> None:
            git("checkout", "-q", "-b", name, "main")
            change()
            git("add", "-A")
            git("commit", "-q", "-m", name)
            git("push", "-q", "origin", name)
            git("checkout", "-q", "main")

        def replace_one(new: str):
            def change() -> None:
                with open(f"{repo}/f.txt", encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
                write(f"{repo}/f.txt", "\n".join(new if ln == "one" else ln for ln in lines))
            return change
        br("h/a/one", replace_one("ONE"))
        br("h/b/two", lambda: write(f"{repo}/g.txt", "new\n"))
        br("h/c/clash", replace_one("uno"))
        if subprocess.run(["git", "remote", "set-head", "origin", "main"], cwd=repo, env=base_env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60).returncode:
            git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        git("checkout", "-q", "-b", "local-work", "main")
        write(f"{repo}/f.txt", "dirty\n", "a")   # the caller's own state, uncommitted

        def snap() -> str:
            return (git("rev-parse", "HEAD") + git("status", "--porcelain")
                    + git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads") + git("diff"))
        before = snap()

        def origin_refs() -> str:
            return git("--git-dir", origin, "for-each-ref", "--format=%(refname) %(objectname)", cwd=sandbox)
        origin_before = origin_refs()

        def leftovers() -> str:
            return git("worktree", "list") + "\n".join(os.listdir(scratch))

        def clean() -> bool:
            return (before == snap() and not os.listdir(scratch)
                    and len(git("worktree", "list").rstrip("\n").split("\n")) == 1)

        def run(*args: str, path_first: str = "", **env: str) -> tuple[int, str]:
            e = {**base_env, "TMPDIR": scratch, "AGENT_FABRIC_TRIAL_MIN_FREE_KB": "0", **env}
            if path_first:
                e["PATH"] = f"{path_first}:{e.get('PATH', '')}"
            r = subprocess.run(["bash", UNDER_TEST, *args], cwd=repo, env=e, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=300)
            return r.returncode, r.stdout

        trial = f"{sandbox}/trial.json"

        def cfg(text: str) -> None:
            write(trial, text)

        def checked(*args: str, **env: str) -> tuple[int, str]:
            return run(*args, AGENT_FABRIC_TRIAL_CONFIG=trial, **env)

        def as_json(text: str) -> dict:
            try:
                d = json.loads(text)
                return d if isinstance(d, dict) else {}
            except ValueError:
                return {}

        print("trial-merge: combine, conflict, the project's check, and nothing left behind")
        rc, out = run("h/a/one", "h/b/two", "--json")
        d = as_json(out)
        check("two independent branches combine: exit 0, a tree hash, the shas tried",
              rc == 0 and d.get("result") == "combines" and len(d.get("tree") or "") == 40
              and [r.get("branch") for r in d.get("refs") or []] == ["h/a/one", "h/b/two"], f"rc={rc}\n{out}")
        check("…the caller's HEAD, index, working tree and branches untouched; no worktree left", clean(), leftovers())
        manual_dir = f"{sandbox}/m"
        subprocess.run(["git", "clone", "-q", origin, manual_dir], env=base_env, check=True, timeout=60)
        for ref in ("origin/h/a/one", "origin/h/b/two"):
            git("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "--no-edit", ref, cwd=manual_dir)
        manual = git("rev-parse", "HEAD^{tree}", cwd=manual_dir).strip()
        shutil.rmtree(manual_dir)
        check("…the reported tree is the tree of the same merges made by hand, in the order given",
              d.get("tree") == manual, f"{manual} vs {d.get('tree')}")
        check("…and the remote's refs are unchanged: nothing pushed", origin_before == origin_refs())

        rc, out = run("h/a/one", "h/c/clash")
        check("the same line changed twice: conflicts, naming the second ref and the path; exit 1",
              rc == 1 and "conflicts — h/c/clash did not merge" in out and "    f.txt" in out, f"rc={rc}\n{out}")
        check("…and nothing left behind", clean(), leftovers())

        cfg('{"check": ["sh", "-c", "test -f g.txt && grep -q ONE f.txt"]}')
        rc, out = checked("h/a/one", "h/b/two", "--check")
        check("--check runs the project's check on the combined tree: passed",
              rc == 0 and "check passed (exit 0)" in out, f"rc={rc}\n{out}")
        cfg('{"check": ["sh", "-c", "echo building; echo the suite failed >&2; exit 3"]}')
        rc, out = checked("h/a/one", "--check")
        check("…failed: exit 1 with its last lines",
              rc == 1 and "check failed (exit 3)" in out and "the suite failed" in out, f"rc={rc}\n{out}")
        check("…and nothing left behind", clean(), leftovers())
        cfg('{"check": ["sleep", "30"], "timeout_s": 1}')
        rc, out = checked("h/a/one", "--check")
        check("…timed out: unavailable, exit 2 — never a pass", rc == 2 and "check unavailable" in out, f"rc={rc}\n{out}")
        cfg('{"check": ["no-such-check-command"]}')
        rc, out = checked("h/a/one", "--check")
        check("…a check command that is not there: unavailable", rc == 2 and "check unavailable" in out,
              f"rc={rc}\n{out}")
        verdict = '"verdict": "^trial-check: (PASS|FAIL|UNAVAILABLE)"'
        cfg(f'{{"check": ["sh", "-c", "echo \'trial-check: PASS on x\'; exit 2"], {verdict}}}')
        rc, out = checked("h/a/one", "--check")
        check("a declared verdict line wins over the exit code: PASS with exit 2 is a pass",
              rc == 0 and "check passed" in out, f"rc={rc}\n{out}")
        cfg(f'{{"check": ["sh", "-c", "echo \'trial-check: FAIL on x\'; exit 0"], {verdict}}}')
        rc, out = checked("h/a/one", "--check")
        check("…FAIL with exit 0 is a failure", rc == 1 and "check failed" in out, f"rc={rc}\n{out}")
        cfg(f'{{"check": ["sh", "-c", "echo \'trial-check: UNAVAILABLE on x\'; exit 2"], {verdict}}}')
        rc, out = checked("h/a/one", "--check")
        check("…UNAVAILABLE is unavailable", rc == 2 and "check unavailable" in out, f"rc={rc}\n{out}")
        cfg(f'{{"check": ["sh", "-c", "echo make: no rule to make target; exit 0"], {verdict}}}')
        rc, out = checked("h/a/one", "--check")
        check("…a declared verdict that never appears is unavailable, even on exit 0",
              rc == 2 and "check unavailable" in out, f"rc={rc}\n{out}")
        rc, out = checked("h/a/one", "h/c/clash", "--check")
        check("…not run on refs that conflict, and said",
              rc == 1 and "check: not run — the refs did not combine" in out, f"rc={rc}\n{out}")
        cfg("{}")
        rc, out = checked("h/a/one", "--check")
        check("…a project that declares none: merge only, and said", rc == 0 and "none declared" in out,
              f"rc={rc}\n{out}")

        cfg('{"check": ["sleep", "37.25"]}')   # a sentinel no other process runs
        # The script's own process is the one signalled (a wrapper around it
        # would take the signal and leave the script running to its end).
        for sig, label in ((signal.SIGTERM, "a run killed (TERM) during the check leaves no worktree and no file"),
                           (signal.SIGINT, "…and interrupted (INT): the same — the caller's uncommitted edit and "
                                           "worktree list as they were")):
            victim = subprocess.Popen(["bash", UNDER_TEST, "h/a/one", "--check"], cwd=repo,
                                      env={**base_env, "TMPDIR": scratch, "AGENT_FABRIC_TRIAL_MIN_FREE_KB": "0",
                                           "AGENT_FABRIC_TRIAL_CONFIG": trial},
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(50):
                if os.listdir(scratch):
                    break
                time.sleep(0.1)
            for _ in range(50):
                if sentinel_running("sleep 37.25"):
                    break
                time.sleep(0.1)
            victim.send_signal(sig)
            victim.wait(timeout=60)
            time.sleep(0.5)
            if sig == signal.SIGTERM:
                check(label, clean(), leftovers())
                alive = sentinel_running("sleep 37.25")
                check("…and no check process: the check's whole group went with it", not alive)
            else:
                alive = sentinel_running("sleep 37.25")
                check(label, clean() and not alive, leftovers())
            if alive:
                end_sentinel("sleep 37.25")

        # A worktree add that loses a race once (another run's prune, a
        # config lock) is retried, not reported as a failed trial: a git that
        # fails the first add and then behaves (CI, #52, "concurrent runs
        # disagreed").
        flaky, count = f"{sandbox}/flakybin", f"{sandbox}/flaky.count"
        os.makedirs(flaky)
        write(f"{flaky}/git", "#!/usr/bin/env bash\n"
              f'if [[ "$*" == *"worktree add"* && ! -f "{count}" ]]; then\n'
              f'    : > "{count}"; echo "fatal: could not lock config file .git/config: File exists" >&2; exit 128\n'
              "fi\n"
              f'exec "{shutil.which("git")}" "$@"\n')
        os.chmod(f"{flaky}/git", 0o755)
        rc, out = run("h/a/one", "h/b/two", "--json", path_first=flaky)
        check("a worktree add that fails once is retried, and the trial runs",
              rc == 0 and os.path.isfile(count) and as_json(out).get("result") == "combines", out)
        check("…and the retry left nothing", clean(), leftovers())

        both = [subprocess.Popen(["bash", UNDER_TEST, "h/a/one", "h/b/two", "--json"], cwd=repo,
                                 env={**base_env, "TMPDIR": scratch, "AGENT_FABRIC_TRIAL_MIN_FREE_KB": "0"},
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(2)]
        r1, r2 = (as_json(p.communicate(timeout=300)[0]) for p in both)
        check("two runs at once on the same refs: each its own worktree, the same result",
              r1.get("tree") is not None and r1.get("tree") == r2.get("tree") and r1.get("result") == "combines",
              f"{r1}\n{r2}")
        check("…and neither left anything", clean(), leftovers())

        rc, out = run("h/a/one", "h/zz/nowhere")
        check("a ref not on origin: exit 2, nothing tried, nothing left",
              rc == 2 and "h/zz/nowhere is not a branch on origin; nothing tried" in out and clean(), f"rc={rc}\n{out}")
        git("remote", "set-url", "origin", f"{sandbox}/nowhere.git")
        rc, out = run("h/a/one")
        git("remote", "set-url", "origin", origin)
        check("a failed fetch: exit 2, nothing tried", rc == 2 and "git fetch origin failed; nothing tried" in out,
              f"rc={rc}\n{out}")
        rc, out = run("h/a/one", AGENT_FABRIC_TRIAL_MIN_FREE_KB="999999999999")
        check("too little free space: refused before starting", rc == 2 and "nothing tried" in out and "KB free" in out,
              f"rc={rc}\n{out}")
        rc, out = run()
        check("no ref named: a usage error", rc == 2, f"rc={rc}\n{out}")

        print("trial-merge: the review of #47's cases")
        # A clone whose hooks refuse every commit (every managed clone runs
        # hooks): the trial merge is never committed anywhere, so the hooks
        # are not run.
        hooks = f"{sandbox}/hooks"
        os.makedirs(hooks)
        for hook in ("commit-msg", "pre-merge-commit"):
            write(f"{hooks}/{hook}", '#!/bin/sh\necho "hook: refused" >&2\nexit 1\n')
            os.chmod(f"{hooks}/{hook}", 0o755)
        git("config", "core.hooksPath", hooks)
        rc, out = run("h/a/one", "h/b/two")
        git("config", "--unset", "core.hooksPath")
        check("a clone whose hooks refuse commits: the refs still combine — no hook runs on a trial merge",
              rc == 0 and any(line.startswith("combines") for line in out.split("\n")), f"rc={rc}\n{out}")
        # A branch with no history in common: not a conflict, and never said
        # to be one.
        git("stash", "-q")
        git("checkout", "-q", "--orphan", "h/d/alien")
        git("rm", "-rfq", ".")
        write(f"{repo}/alien.txt", "x\n")
        git("add", "-A")
        git("commit", "-q", "-m", "alien")
        git("push", "-q", "origin", "h/d/alien")
        git("checkout", "-q", "-f", "local-work")
        git("stash", "pop", "-q")
        before = snap()
        rc, out = run("h/a/one", "h/d/alien", "--json")
        d = as_json(out)
        check("unrelated histories: 'could not merge' with git's line, exit 2 — never 'conflicts'",
              rc == 2 and d.get("result") == "could not merge" and len(d.get("conflicted") or []) == 0
              and "unrelated histories" in (d.get("git") or ""), f"rc={rc}\n{out}")
        check("…and nothing left behind", clean(), leftovers())
        # A check that starts something in the background and exits 0.
        cfg('{"check": ["sh", "-c", "sleep 41.75 & exit 0"]}')
        checked("h/a/one", "--check")
        time.sleep(0.3)
        alive = sentinel_running("sleep 41.75")
        check("a check that left a process behind and exited: its whole group is gone too", not alive)
        if alive:
            end_sentinel("sleep 41.75")
        # A held lease (fabric-lease's exit 75) is unavailable, never a
        # failure.
        cfg('{"check": ["sh", "-c", "exit 75"]}')
        rc, out = checked("h/a/one", "--check")
        check("a lease still held (75): unavailable", rc == 2 and "check unavailable" in out, f"rc={rc}\n{out}")
        # A dead run's leftovers — its worktree, pid and output files — are
        # swept by the next run.
        os.makedirs(f"{scratch}/trial-merge.DEAD01")
        write(f"{scratch}/trial-merge.DEAD01.pid", "999999\n")
        write(f"{scratch}/trial-merge.DEAD01.out", "old\n")
        run("h/a/one")
        check("a dead run's worktree, pid and output file are swept by the next run", not os.listdir(scratch),
              "\n".join(os.listdir(scratch)))

        print("trial-merge: the re-review of #47's cases")
        # A declared lease runs the check in a group of its own, as
        # fabric-lease does (set -m around the child): the check's leftovers
        # are ended anyway.
        leasebin = f"{sandbox}/leasebin"
        os.makedirs(leasebin)
        write(f"{leasebin}/fabric-lease", '#!/usr/bin/env bash\nshift; [[ "$1" == "--" ]] && shift\n'
              'set -m; "$@" & child=$!; set +m\nwait "$child"\n')
        os.chmod(f"{leasebin}/fabric-lease", 0o755)
        cfg('{"check": ["sh", "-c", "cd / && sleep 43.5 & exit 0"], "lease": "trial"}')   # it leaves the worktree, too
        rc, out = checked("h/a/one", "--check", path_first=leasebin)
        time.sleep(0.3)
        check("…a check under a declared lease runs and passes", rc == 0 and "check passed" in out, f"rc={rc}\n{out}")
        alive = sentinel_running("sleep 43.5")
        check("…and what it left running in its own group under the lease is ended too", not alive)
        if alive:
            end_sentinel("sleep 43.5")
        check("…nothing left behind", clean(), leftovers())
        # The check on refs that did not merge says so, whatever the reason.
        cfg('{"check": ["true"]}')
        rc, out = checked("h/a/one", "h/d/alien", "--check", "--json")
        check("a merge that failed without a conflict: its check reads 'not run: did not combine'",
              rc == 2 and as_json(out).get("check") == "not run: did not combine", f"rc={rc}\n{out}")
        # A worktree left without a pid by a run killed before writing it:
        # swept once an hour old.
        os.makedirs(f"{scratch}/trial-merge.NOPID1")
        two_hours_ago = time.time() - 7200
        os.utime(f"{scratch}/trial-merge.NOPID1", (two_hours_ago, two_hours_ago))
        os.makedirs(f"{scratch}/trial-merge.NOPID2")
        run("h/a/one")
        check("a pid-less worktree an hour old is swept; a fresh one (a run just starting) is left",
              not os.path.exists(f"{scratch}/trial-merge.NOPID1") and os.path.isdir(f"{scratch}/trial-merge.NOPID2"),
              "\n".join(os.listdir(scratch)))
        shutil.rmtree(f"{scratch}/trial-merge.NOPID2")

    print(f"\ntest_trial_merge_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
