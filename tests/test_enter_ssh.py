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


def run(tmp: str, request: str | None, client: str | None = None) -> subprocess.CompletedProcess[str]:
    return run_pid(tmp, request, client)[0]


def run_pid(tmp: str, request: str | None, client: str | None = None) -> tuple[subprocess.CompletedProcess[str], int]:
    """The run and its pid: the script execs, so the pid it keys its client record by is the child's."""
    env = {"PATH": "/usr/bin:/bin", "HOME": os.path.join(tmp, "home"), "LANG": "C"}
    if request is not None:
        env["SSH_ORIGINAL_COMMAND"] = request
    if client is not None:
        env["SSH_CLIENT"] = client
    with subprocess.Popen([os.path.join(tmp, "bin", "enter-ssh")], env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL) as p:
        out, err = p.communicate(timeout=30)
        return subprocess.CompletedProcess(p.args, p.returncode, out, err), p.pid


def write_conf(tmp: str, text: str | None) -> None:
    conf = os.path.join(tmp, "bin", "enter-ssh.conf")
    if text is None:
        if os.path.exists(conf):
            os.remove(conf)
        return
    with open(conf, "w", encoding="utf-8") as fh:
        fh.write(text)
    # The mode enter-ssh demands, set here rather than left to the runner's
    # umask: a CI container's 000 makes the file group-writable, and refused.
    os.chmod(conf, 0o644)


def setup(tmp: str) -> None:
    bindir = os.path.join(tmp, "bin")
    home = os.path.join(tmp, "home")
    os.makedirs(bindir)
    os.makedirs(os.path.join(home, "projects"))
    # enter-ssh insists its conf and enter are owned by uid 0, and a test
    # cannot make files root-owned: the installed copy has the constant at its
    # top rewritten with sed to the test's uid. Everything else is verbatim.
    dst = os.path.join(bindir, "enter-ssh")
    shutil.copy2(UNDER_TEST, dst)
    subprocess.run(["sed", "-i", f"s/^EXPECTED_OWNER_UID=0$/EXPECTED_OWNER_UID={os.getuid()}/", dst], check=True)
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
        # The mode fence (the owner uid is rewritten in setup, see there).
        write_conf(tmp, os.path.join(tmp, "share", "enter") + "\n")
        conf = os.path.join(tmp, "bin", "enter-ssh.conf")
        enter = os.path.join(tmp, "share", "enter")
        for label, path, mode in (("a group-writable conf", conf, 0o664), ("an other-writable conf", conf, 0o602),
                                  ("a group-writable enter", enter, 0o775), ("an other-writable enter", enter, 0o757)):
            os.chmod(path, mode)
            r = run(tmp, "--watch")
            check(f"{label}: exit 1, one line, no enter run",
                  r.returncode == 1 and r.stdout == "" and len(r.stderr.splitlines()) == 1
                  and "not owned by root" in r.stderr, f"rc={r.returncode} {r.stdout!r} {r.stderr!r}")
            os.chmod(path, 0o644 if path == conf else 0o755)
        r = run(tmp, "--watch")
        check("closed to group and others again: runs", r.returncode == 0, f"rc={r.returncode} {r.stderr!r}")
        shutil.copy2(UNDER_TEST, os.path.join(tmp, "bin", "enter-ssh"))  # verbatim: expects owner uid 0
        r = run(tmp, "--watch")
        check("owned by the test user, not root: refused, as for the real script",
              r.returncode == 1 and "not owned by root" in r.stderr and r.stdout == "", f"rc={r.returncode} {r.stderr!r}")
    with tempfile.TemporaryDirectory() as tmp:
        setup(tmp)
        me = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        clients = os.path.join(tmp, "home", ".local", "state", "agent-fabric", "agents", me, "ssh-clients")
        # A dead pid must exceed pid_max (2**22 on a long-running host).
        dead = os.path.join(clients, str(2 ** 22 + 1))
        os.makedirs(clients, mode=0o700)
        for name in (os.path.basename(dead), "notes"):
            with open(os.path.join(clients, name), "w", encoding="utf-8") as fh:
                fh.write("old\n")
        r, pid = run_pid(tmp, "--watch", "192.0.2.7 51234 22")
        rec = os.path.join(clients, str(pid))
        check("SSH_CLIENT is recorded under the pane's pid, and the pane still enters",
              r.returncode == 0 and r.stderr == "" and os.path.isfile(rec) and open(rec, encoding="utf-8").read() == "192.0.2.7 51234 22\n",
              f"rc={r.returncode} {r.stderr!r} {sorted(os.listdir(clients))}")
        check("a dead pane's record is pruned, a file that is no pid's is not",
              not os.path.exists(dead) and os.path.exists(os.path.join(clients, "notes")), str(sorted(os.listdir(clients))))
        before = sorted(os.listdir(clients))
        for label, value in (("unset", None), ("empty", ""), ("a command", "1.2.3.4 5 6;id"), ("two fields", "1.2.3.4 5")):
            r, pid = run_pid(tmp, "--watch", value)
            check(f"SSH_CLIENT {label}: nothing recorded, the pane enters",
                  r.returncode == 0 and sorted(os.listdir(clients)) == before, f"rc={r.returncode} {sorted(os.listdir(clients))}")
        # The record is a convenience: a state dir that cannot be made must not stop the pane.
        shutil.rmtree(os.path.join(tmp, "home", ".local"))
        with open(os.path.join(tmp, "home", ".local"), "w", encoding="utf-8") as fh:
            fh.write("a file where the state dir would be\n")
        r, pid = run_pid(tmp, "--watch", "192.0.2.7 51234 22")
        check("a state dir that cannot be made: the pane enters, silently", r.returncode == 0 and r.stderr == "", f"rc={r.returncode} {r.stderr!r}")
        os.remove(os.path.join(tmp, "home", ".local"))
        os.umask(0o022)  # the dir's mode is the script's, not the runner's umask
        r, pid = run_pid(tmp, "--watch", "192.0.2.7 51234 22")
        check("the record dir the script makes is private",
              os.path.isfile(os.path.join(clients, str(pid))) and os.stat(clients).st_mode & 0o777 == 0o700,
              oct(os.stat(clients).st_mode) if os.path.isdir(clients) else "no dir")
    print(f"\n{'all passed' if not fails else f'{fails} failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
