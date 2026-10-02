#!/usr/bin/env python3
"""runtime/provisioning/rename-working-copy.sh, the shell half of the
rename: it refuses before touching anything, stops where a step fails,
and hands the history to rename_history.py only once the tree is at its
new path. Fakes for sudo (runs the rest as this user), getent (a sandbox
home), pgrep (a live session, when asked) and mv (a failure, when asked);
the Python half is tests/test_rename_history.py. Ported from
runtime/provisioning/test_rename-working-copy.sh (ADR-040 Wave 6), case
for case. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.abspath(os.environ.get("RENAME_WORKING_COPY")
                             or os.path.join(ROOT, "runtime", "provisioning", "rename-working-copy.sh"))
if not os.path.isfile(UNDER_TEST):
    sys.exit(f"test: script under test not found at {UNDER_TEST}")
LOGIN = "zz-rename-fixture"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, fault = f"{sandbox}/bin", f"{sandbox}/fault"
        home = f"{sandbox}/home/{LOGIN}"
        os.makedirs(bin_)
        fakes = {
            "sudo": "#!/usr/bin/env bash\n"
                    '[[ "$1" == -u ]] && shift 2; [[ "$1" == -H ]] && shift\n'
                    f'args=(); for a in "$@"; do [[ "$a" == PATH=* ]] && a="PATH={bin_}:${{a#PATH=}}"; args+=("$a"); done\n'
                    'exec "${args[@]}"\n',
            "getent": "#!/usr/bin/env bash\n"
                      f'[[ "$1" == passwd && "$2" == "{LOGIN}" ]] && {{ echo "{LOGIN}:x:1000:1000::{home}:/bin/bash"; exit 0; }}; '
                      "exit 2\n",
            "pgrep": f'#!/usr/bin/env bash\ngrep -qsxF live "{fault}"\n',
            "mv": "#!/usr/bin/env bash\n"
                  f'grep -qsxF mv "{fault}" && {{ echo "mv: injected failure" >&2; exit 1; }}\n'
                  'exec /usr/bin/mv "$@"\n',
        }
        for name, text in fakes.items():
            with open(f"{bin_}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(f"{bin_}/{name}", 0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env.update(PATH=f"{bin_}:/usr/bin:/bin", SUDO=f"{bin_}/sudo", AGENT_FABRIC_STATE_DIR=f"{home}/state")

        def key(name: str) -> str:
            return f"{home}/.claude/projects/" + f"{home}/projects/{name}".replace("/", "-")

        def put(path: str, text: str, mode: str = "w") -> None:
            with open(path, mode, encoding="utf-8") as fh:
                fh.write(text)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def reset() -> None:
            shutil.rmtree(home, ignore_errors=True)
            if os.path.exists(fault):
                os.remove(fault)
            for d in (f"{home}/projects/old", f"{home}/.claude/projects", f"{home}/state/agents/{LOGIN}"):
                os.makedirs(d)
            old = f"{home}/projects/old"
            for args in (["init", "-q", "-b", "main"], ["add", "f"],
                         ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q",
                          "-m", "init"]):
                if args[0] == "add":
                    put(f"{old}/f", "x\n")
                subprocess.run(["git", "-C", old, *args], env=env, check=True, timeout=30)
            os.symlink(ROOT, f"{home}/projects/agent-fabric")
            os.makedirs(key("old"))
            put(f"{key('old')}/s.jsonl", f'{{"cwd":"{old}"}}\n')

        def rename(*args: str) -> tuple[int, str]:
            r = subprocess.run(["bash", UNDER_TEST, LOGIN, "old", "new", *args], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=120)
            return r.returncode, r.stdout

        print("rename: the whole path")
        reset()
        rc, out = rename()
        check("the tree moved", rc == 0 and os.path.isdir(f"{home}/projects/new/.git")
              and not os.path.lexists(f"{home}/projects/old"), f"rc={rc}\n{out}")
        check("…and the history followed, cwd rewritten",
              os.path.isdir(key("new")) and not os.path.isdir(key("old")) and "projects/new" in read(f"{key('new')}/s.jsonl"),
              out)
        rc, out = rename()
        check("a second run says already at the new path", rc == 0 and "already at" in out, out)

        print("rename: refusals before anything moves")
        reset()
        put(fault, "live\n")
        rc, out = rename()
        check("a live session refuses first; nothing touched",
              rc == 1 and "live claude session" in out and os.path.isdir(f"{home}/projects/old")
              and os.path.isdir(key("old")), out)
        reset()
        put(f"{home}/projects/old/f", "y\n", "a")
        rc, out = rename()
        check("a dirty tree refuses; nothing touched",
              rc == 1 and "uncommitted change" in out and os.path.isdir(f"{home}/projects/old"), out)
        reset()
        os.makedirs(f"{home}/projects/new")
        rc, out = rename()
        check("old and new both present: refused, nothing moved",
              rc == 1 and re.search(r"both .* exist", out) is not None and os.path.isdir(f"{home}/projects/old/.git"), out)

        print("rename: the mv fails")
        reset()
        put(fault, "mv\n")
        rc, out = rename()
        check("stops at the mv, named", rc == 1 and re.search(r"step failed: .*mv", out) is not None,
              f"rc={rc}\n{out}")
        check("…and the history was not rewritten",
              os.path.isdir(f"{home}/projects/old/.git") and os.path.isdir(key("old")) and not os.path.isdir(key("new"))
              and "projects/old" in read(f"{key('old')}/s.jsonl"))
        os.remove(fault)
        rc, out = rename()
        check("…and the retry completes", rc == 0 and os.path.isdir(key("new")), out)

        print("rename: dry run")
        reset()
        rc, out = rename("--dry-run")
        check("reports, touches nothing", rc == 0 and "would: mv" in out and os.path.isdir(f"{home}/projects/old")
              and os.path.isdir(key("old")), out)

    print(f"\ntest_rename_working_copy_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
