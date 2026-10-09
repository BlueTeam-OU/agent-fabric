#!/usr/bin/env python3
"""runtime/provisioning/moveto/enter-ssh, the operator key's forced command
(agent-fabric ADR-048 §5 rule 4).

The script is copied into a scratch directory beside a fake `enter` that
prints its argv and one variable set only by the scratch HOME's ~/.bashrc
(sourced from ~/.bash_profile): so an accepted word shows both what
reached `enter` and that a login shell ran the account's start-up files
first. Every refusal must exit 2 with one line on stderr and never run
`enter`. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.join(ROOT, "runtime", "provisioning", "moveto", "enter-ssh")

FAKE_ENTER = """#!/usr/bin/env bash
printf 'argc=%s\\n' "$#"
for a in "$@"; do printf 'arg=%s\\n' "$a"; done
printf 'bashrc=%s\\n' "${ENTER_SSH_TEST_BASHRC-unset}"
"""

REFUSAL = "enter-ssh: refused; ask for exactly one of --wait, --watch, shell, --resume\n"
ACCEPTED = {"--wait": ["--wait"], "--watch": ["--watch"], "--resume": ["--resume"], "shell": []}
REFUSED = {
    "unset": None, "empty": "", "unknown word": "--help", "unknown option": "--list",
    "two words": "--wait --watch", "trailing space": "shell ", "leading space": " --wait",
    "semicolon": "--wait;id", "semicolon alone": ";", "command substitution": "$(id)",
    "substitution after a word": "--resume$(id)", "backticks": "`id`",
    "newline": "--wait\nid", "trailing newline": "--resume\n", "a command": "id -un",
    "case": "--WAIT", "shell word as option": "--shell",
}


def run(tmp: str, request: str | None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", "HOME": os.path.join(tmp, "home"), "LANG": "C"}
    if request is not None:
        env["SSH_ORIGINAL_COMMAND"] = request
    return subprocess.run([os.path.join(tmp, "bin", "enter-ssh")], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=30)


def write_conf(tmp: str, text: str | None) -> None:
    conf = os.path.join(tmp, "bin", "enter-ssh.conf")
    if text is None:
        if os.path.exists(conf):
            os.remove(conf)
        return
    with open(conf, "w", encoding="utf-8") as fh:
        fh.write(text)


def setup(tmp: str) -> None:
    bindir = os.path.join(tmp, "bin")
    home = os.path.join(tmp, "home")
    os.makedirs(bindir)
    os.makedirs(os.path.join(home, "projects"))
    shutil.copy2(UNDER_TEST, os.path.join(bindir, "enter-ssh"))
    # The fake enter is NOT beside enter-ssh: only the conf line may name it.
    share = os.path.join(tmp, "share")
    os.makedirs(share)
    for d in (share, bindir):
        with open(os.path.join(d, "enter"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_ENTER if d == share else "#!/bin/sh\necho SIBLING-ENTER-RAN\n")
        os.chmod(os.path.join(d, "enter"), 0o755)
    write_conf(tmp, os.path.join(share, "enter") + "\n")
    with open(os.path.join(home, ".bash_profile"), "w", encoding="utf-8") as fh:
        fh.write('[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"\n')
    with open(os.path.join(home, ".bashrc"), "w", encoding="utf-8") as fh:
        fh.write("export ENTER_SSH_TEST_BASHRC=ran\n")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"      {detail}")
            fails += 1

    with tempfile.TemporaryDirectory() as tmp:
        setup(tmp)
        me = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        home = os.path.join(tmp, "home")
        for word, tail in ACCEPTED.items():
            r = run(tmp, word)
            want = "".join(f"arg={a}\n" for a in [os.path.join(home, "projects"), me, *tail])
            want = f"argc={2 + len(tail)}\n{want}bashrc=ran\n"
            check(f"accepts {word}: enter gets <workspace> <login>{' ' + word if tail else ''}, after ~/.bashrc",
                  r.returncode == 0 and r.stdout == want and r.stderr == "",
                  f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r} want={want!r}")
        for label, request in REFUSED.items():
            r = run(tmp, request)
            check(f"refuses {label}: exit 2, the one fixed line on stderr (the request never echoed), enter not run",
                  r.returncode == 2 and r.stdout == "" and r.stderr == REFUSAL,
                  f"rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
        for label, conf in (("no conf", None), ("an empty conf", ""), ("a relative path", "share/enter\n"),
                            ("a missing enter", os.path.join(tmp, "nowhere", "enter") + "\n")):
            write_conf(tmp, conf)
            r = run(tmp, "--watch")
            check(f"{label}: exit 1, one line, no enter run (never the sibling)",
                  r.returncode == 1 and r.stdout == "" and len(r.stderr.splitlines()) == 1
                  and r.stderr.startswith("enter-ssh: no installed enter"), f"rc={r.returncode} {r.stdout!r} {r.stderr!r}")
    print(f"\n{'all passed' if not fails else f'{fails} failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
