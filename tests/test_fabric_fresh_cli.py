#!/usr/bin/env python3
"""bin/fabric-fresh: an agent ends its own session at the end of a job;
the launcher starts a fresh one. Ported from tests/test_fabric-fresh.sh
(ADR-040 Wave 6), case for case.

A fake parent named `claude` (a script's process name is its file name)
runs the command, and AGENT_FABRIC_FRESH_KILL records the stop instead
of sending it, so the suite checks the target without stopping anything.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import datetime
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.abspath(os.environ.get("FABRIC_FRESH") or os.path.join(ROOT, "bin", "fabric-fresh"))
if not os.path.isfile(CMD):
    sys.exit(f"test: script under test not found at {CMD}")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
    env.update(extra)
    return env


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        bin_, state, wc = f"{t}/bin", f"{t}/state", f"{t}/wc"
        for d in (bin_, state, wc):
            os.makedirs(d)
        killed, claude_pid = f"{t}/killed", f"{t}/claude.pid"
        marker = f"{state}/agents/{LOGIN}/restart.json"

        def put(path: str, text: str, mode: int = 0o755) -> None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def rm(*paths: str) -> None:
            for p in paths:
                if os.path.lexists(p):
                    os.remove(p)

        put(f"{bin_}/record-kill", f'#!/usr/bin/env bash\necho "$*" > "{killed}"\n')
        # A real process named claude-fake (a copied bash: a script's process
        # name is its interpreter's), never "claude": this suite runs inside a
        # session.
        shutil.copy(shutil.which("bash"), f"{bin_}/claude-fake")
        put(f"{bin_}/claude",
            "#!/usr/bin/env bash\n"
            f"exec \"{bin_}/claude-fake\" -c 'echo $$ > \"{claude_pid}\"; cd \"{wc}\" && \"{CMD}\" \"$@\"' claude-fake \"$@\"\n")
        git = ["git", "-C", wc]
        subprocess.run([*git, "init", "-q"], check=True, timeout=30)
        put(f"{wc}/f", "a\n", 0o644)
        subprocess.run([*git, "add", "f"], check=True, timeout=30)
        subprocess.run([*git, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "a"], check=True, timeout=30)
        envs = {"AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_FRESH_KILL": f"{bin_}/record-kill",
                "AGENT_FABRIC_FRESH_COMM": "claude-fake", "AGENT_FABRIC_LAUNCH_OPENING": "1"}
        # The fabric checkout the launcher's verdict is asked of: no git
        # at all (the verdict is "skip") until the currency cases below,
        # never this tree, whose origin the suite must not fetch.
        fab = f"{t}/fabric"
        os.makedirs(fab)
        envs["AGENT_FABRIC_ROOT"] = fab
        launched = {"AGENT_FABRIC_LAUNCH_PROFILE": "p", **envs}

        def run(argv: list[str], env: dict, cwd: str | None = None) -> tuple[int, str]:
            r = subprocess.run(argv, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=60)
            return r.returncode, r.stdout

        print("fabric-fresh: --help names every refusal and prints no code")
        rc, out = run([CMD, "--help"], clean_env())
        check("the five refusals, and the header ends before the code",
              rc == 0 and all(s in out for s in ("not started by the launcher", "uncommitted changes",
                                                  "its own prompt or -p", "predates fabric-fresh",
                                                  "no claude process", "--job <id>"))
              and "set -uo" not in out and not any(line.startswith("note=") for line in out.splitlines()),
              f"rc={rc}\n{out}")

        print("fabric-fresh: refused where nothing would bring a session back")
        rc, out = run([f"{bin_}/claude"], clean_env(**envs))
        check("not launched: exit 2, nothing stopped",
              rc == 2 and "not started by the launcher" in out and not os.path.exists(killed), f"rc={rc}\n{out}")

        print("fabric-fresh: refused where the launch carried its own prompt")
        rc, out = run([f"{bin_}/claude"], clean_env(**{**launched, "AGENT_FABRIC_LAUNCH_OPENING": "0"}))
        check("own prompt: exit 2, nothing stopped",
              rc == 2 and "launched with its own prompt" in out and not os.path.exists(killed), f"rc={rc}\n{out}")

        old = {k: v for k, v in launched.items() if k != "AGENT_FABRIC_LAUNCH_OPENING"}
        rc, out = run([f"{bin_}/claude"], clean_env(**old))
        check("a launcher older than fabric-fresh: exit 2, said as such",
              rc == 2 and "launcher predates fabric-fresh" in out and not os.path.exists(killed), f"rc={rc}\n{out}")

        print("fabric-fresh: a job with uncommitted changes is not done")
        put(f"{wc}/untracked", "new\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("an untracked file counts: exit 3", rc == 3 and not os.path.exists(killed), f"rc={rc}\n{out}")
        rm(f"{wc}/untracked")
        with open(f"{wc}/f", "a", encoding="utf-8") as fh:
            fh.write("b\n")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("dirty tree: exit 3, no marker, nothing stopped",
              rc == 3 and "uncommitted changes" in out and not os.path.exists(killed)
              and not os.path.exists(marker), f"rc={rc}\n{out}")
        rc, out = run([f"{bin_}/claude", "--force"], clean_env(**launched))
        check("…--force goes ahead", rc == 0 and os.path.exists(killed), f"rc={rc}\n{out}")
        subprocess.run([*git, "checkout", "-q", "--", "f"], check=True, timeout=30)
        rm(killed, marker)

        print("fabric-fresh: the marker the launcher reads, and the stop of the session above")
        rc, out = run([f"{bin_}/claude", "--note", "PR  981 merged"], clean_env(**launched))
        check("clean tree: exit 0, marker written", rc == 0 and os.path.isfile(marker), f"rc={rc}\n{out}")
        try:
            m = json.loads(read(marker))
            datetime.datetime.fromisoformat(m["requested_at"].replace("Z", "+00:00"))
            good = m["fresh"] is True and m["status"] == "done" and m["note"] == "PR 981 merged"
        except (ValueError, KeyError, TypeError):
            good = False
        check("…fresh, done, the note on one line, requested_at a date", good, read(marker))
        check("…and SIGTERM goes to the claude process above it",
              read(killed).rstrip("\n") == f"-TERM {read(claude_pid).strip()}",
              f"killed: {read(killed)} claude: {read(claude_pid)}")

        print("fabric-fresh: a stop that fails takes its marker back")
        rm(marker)
        rc, out = run([f"{bin_}/claude"], clean_env(**{**launched, "AGENT_FABRIC_FRESH_KILL": "false"}))
        check("exit 1, no marker left for the next plain exit",
              rc == 1 and not os.path.exists(marker) and "could not stop" in out, f"rc={rc}\n{out}")
        # An upgrade's marker written between ours and the failed stop is not
        # ours to remove.
        put(f"{bin_}/kill-then-upgrade",
            "#!/usr/bin/env bash\n"
            f"echo '{{\"requested_at\":\"2099-01-01T00:00:00Z\",\"piece\":\"fabric\",\"status\":\"pending\"}}' > \"{marker}\"\n"
            "exit 1\n")
        rc, out = run([f"{bin_}/claude"], clean_env(**{**launched, "AGENT_FABRIC_FRESH_KILL": f"{bin_}/kill-then-upgrade"}))
        check("…and an upgrade marker written since is left alone",
              rc == 1 and '"piece":"fabric"' in read(marker), f"rc={rc}\n{read(marker)}")
        rm(marker)

        print("fabric-fresh: --job names the job the next session is for")
        rm(killed)
        rc, out = run([f"{bin_}/claude", "--job", "j9"], clean_env(**launched))
        check("an unknown job: exit 2, no marker, nothing stopped",
              rc == 2 and not os.path.exists(marker) and not os.path.exists(killed) and "no job j9" in out,
              f"rc={rc}\n{out}")
        subprocess.run([os.path.join(ROOT, "bin", "fabric-jobs"), "add", "the next one"], cwd=wc,
                       env=clean_env(AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=state),
                       stdout=subprocess.DEVNULL, check=True, timeout=60)
        rc, out = run([f"{bin_}/claude", "--job", "j1"], clean_env(**launched))
        try:
            m = json.loads(read(marker))
            good = m["fresh"] is True and m["job"] == "j1"
        except (ValueError, KeyError, TypeError):
            good = False
        check("a listed job: its id in the marker, and said",
              rc == 0 and good and "starts a fresh one for job j1" in out, f"rc={rc}\n{out} {read(marker)}")
        rm(marker, killed)

        print("fabric-fresh: refused where the launcher would refuse the relaunch")
        origin, other = f"{t}/origin.git", f"{t}/other"
        gitc = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

        def g(repo: str, *a: str) -> None:
            subprocess.run([*gitc, "-C", repo, *a], check=True, timeout=60, stdout=subprocess.DEVNULL)
        g(fab, "init", "-q", "-b", "main")
        put(f"{fab}/a", "1\n", 0o644)
        put(f"{fab}/b", "1\n", 0o644)
        g(fab, "add", "-A")
        g(fab, "commit", "-q", "-m", "base")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True, timeout=30)
        g(fab, "remote", "add", "origin", origin)
        g(fab, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", origin, other], check=True, timeout=60, stderr=subprocess.DEVNULL)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("a current checkout: the relaunch is fine", rc == 0 and os.path.exists(killed), f"rc={rc}\n{out}")
        rm(killed, marker)
        put(f"{other}/a", "2\n", 0o644)
        g(other, "commit", "-q", "-am", "newer")
        g(other, "push", "-q", "origin", "main")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind and fast-forwardable: the launcher pulls, so fine", rc == 0 and os.path.exists(killed), f"rc={rc}\n{out}")
        rm(killed, marker)
        put(f"{fab}/b", "local\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, a dirty file the pull does not touch: still fine", rc == 0 and os.path.exists(killed), f"rc={rc}\n{out}")
        rm(killed, marker)
        put(f"{fab}/a", "local\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, a dirty file the pull overwrites: exit 3, nothing stopped, no marker",
              rc == 3 and "would refuse the relaunch" in out and "uncommitted changes would be overwritten (a)" in out
              and not os.path.exists(killed) and not os.path.exists(marker), f"rc={rc}\n{out}")
        rc, out = run([f"{bin_}/claude", "--force"], clean_env(**launched))
        check("…--force does not override it", rc == 3 and not os.path.exists(killed), f"rc={rc}\n{out}")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched, AGENT_FABRIC_ALLOW_STALE="1"))
        check("…nor does AGENT_FABRIC_ALLOW_STALE=1 here: the launcher's environment is not this process's",
              rc == 3 and not os.path.exists(killed), f"rc={rc}\n{out}")
        subprocess.run(["git", "-C", fab, "checkout", "-q", "--", "a", "b"], check=True, timeout=30)
        # The pull's changes as git lists them with rename detection off:
        # an incoming rename b -> b2 writes b's removal, and a new directory
        # collides with an untracked file inside it.
        g(other, "mv", "b", "b2")
        os.makedirs(f"{other}/newdir")
        put(f"{other}/newdir/x", "1\n", 0o644)
        g(other, "add", "-A")
        g(other, "commit", "-q", "-m", "rename and new dir")
        g(other, "push", "-q", "origin", "main")
        put(f"{fab}/b", "local\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, a dirty file the pull renames away: exit 3",
              rc == 3 and "overwritten (b" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        subprocess.run(["git", "-C", fab, "checkout", "-q", "--", "b"], check=True, timeout=30)
        os.makedirs(f"{fab}/newdir")
        put(f"{fab}/newdir/x", "mine\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, an untracked file inside a directory the pull adds: exit 3",
              rc == 3 and "newdir/x" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        shutil.rmtree(f"{fab}/newdir")
        # An untracked file where the pull needs a directory (newdir is the
        # pull's), and an untracked directory where it puts a file.
        put(f"{fab}/newdir", "a file\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, an untracked file where the pull adds a directory: exit 3",
              rc == 3 and "overwritten (newdir" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        rm(f"{fab}/newdir")
        # The reverse: the pull adds a FILE where the checkout has an untracked
        # directory. pull_blocker reads status with --untracked-files=all, so the
        # dirty path is "newfile/x", under the touched "newfile": the clause that
        # reads a dirty path under a touched one.
        put(f"{other}/newfile", "1\n", 0o644)
        g(other, "add", "-A")
        g(other, "commit", "-q", "-m", "a new file")
        g(other, "push", "-q", "origin", "main")
        os.makedirs(f"{fab}/newfile")
        put(f"{fab}/newfile/x", "mine\n", 0o644)
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, an untracked directory where the pull adds a file: exit 3, the file inside it named",
              rc == 3 and "overwritten (newfile/x)" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        shutil.rmtree(f"{fab}/newfile")
        g(fab, "mv", "a", "a-moved")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind, a staged rename whose source the pull modifies: exit 3, the source named",
              rc == 3 and "overwritten (a" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        g(fab, "reset", "-q", "--hard")
        g(fab, "commit", "-q", "--allow-empty", "-m", "local")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("behind with a local commit: exit 3, said why, nothing stopped",
              rc == 3 and "local commits that origin/main does not contain" in out and not os.path.exists(killed), f"rc={rc}\n{out}")
        g(fab, "remote", "set-url", "origin", f"{t}/nonexistent.git")
        rc, out = run([f"{bin_}/claude"], clean_env(**launched))
        check("origin unreachable: the launcher launches on what is checked out, so fine",
              rc == 0 and os.path.exists(killed), f"rc={rc}\n{out}")
        rm(killed, marker)

        print("fabric-fresh: no claude above it")
        rc, out = run([CMD], clean_env(**launched), cwd=wc)
        check("exit 2, nothing stopped", rc == 2 and "no claude-fake process" in out, f"rc={rc}\n{out}")

    print(f"\ntest_fabric_fresh_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
