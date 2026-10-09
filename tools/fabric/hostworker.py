#!/usr/bin/env python3
"""runtime/hostexec/worker — run one command on THIS host, as this login
or as another account. The half of the host executor that stands on
the target: `hostexec` runs it directly for the host it is on, and over
ssh for every other, so the same lines do the same thing wherever the
account lives.

  worker [--as <login>] [--cwd <dir>] -- <cmd> [args...]

As the operator (no --as, or --as the caller's own login): the command
runs as is, in the caller's environment. As another account: through
sudo, with a clean environment — HOME from the passwd entry, a fixed
PATH plus the account's ~/.local/bin, cwd its home (or --cwd) — the
idiom every provisioning tool used inline until 2026-09-16
(the retired Doppler enrolment, new-agent.sh as_login,
rename-working-copy.sh as); one place now. stdin, stdout,
stderr and the exit status are the command's: a token piped in and a
bundle streamed out pass through untouched and never appear in argv.

An argument beginning `@fabric/` names a path under a fabric checkout
on THIS host: the operator's (the one this worker sits in) when the
command runs as the operator, the ACCOUNT's own (~/projects/
agent-fabric, which provisioning clones first) when it runs as another
account — the operator's home is not readable to it. The caller need
not know where either is, and nothing expands ~ on the far side.

$SUDO names the sudo to use (a test puts a fake here); the real one is
`sudo -n`: a password prompt is a failure, never a wait.

Contract (ADR-040 Wave 9; ported from the bash worker, which this keeps):
  argv    --as X | --as=X, --cwd D | --cwd=D, then `--` and the command;
          -h/--help prints this text; anything else before `--` is exit 2.
  env     SUDO (split on white space, as the shell's unquoted expansion
          split it); the command's own environment as the operator.
  exit    the command's own (exec: the worker is gone); 2 for a usage
          error, an unknown login or an account with no fabric checkout;
          1 when --cwd cannot be entered; 127/126 for a command that is
          not found / not executable, as the shell's exec said.
"""
from __future__ import annotations

import os
import pwd
import signal
import socket
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
# The account-side stub: checks the account's checkout from inside its own
# shell (its home is 700, invisible to the operator) and enters the cwd.
# Its arguments are the command, never re-parsed.
ACCOUNT_STUB = '''if [ "$1" = 1 ] && [ ! -d "$2" ]; then echo "worker: $(id -un) has no fabric checkout at $2 on $(hostname -s) (provision it first)" >&2; exit 2; fi
             cd "${3:-$HOME}" && shift 3 && exec "$@"'''


def help_text() -> str:
    return (__doc__ or "").split("\n\nContract", 1)[0] + "\n"


def usage_error(msg: str) -> int:
    print(f"worker: {msg}", file=sys.stderr)
    return 2


def short_hostname() -> str:
    return socket.gethostname().split(".")[0]


def parse(argv: list[str]) -> tuple[str, str, list[str]] | int:
    """(as, cwd, command), or the exit status of a help or usage error."""
    as_login = cwd = ""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--as", "--cwd"):
            if i + 1 >= len(argv):
                return usage_error(f"{a} needs a value")
            if a == "--as":
                as_login = argv[i + 1]
            else:
                cwd = argv[i + 1]
            i += 2
        elif a.startswith("--as="):
            as_login, i = a[len("--as="):], i + 1
        elif a.startswith("--cwd="):
            cwd, i = a[len("--cwd="):], i + 1
        elif a == "--":
            i += 1
            break
        elif a in ("-h", "--help"):
            sys.stdout.write(help_text())
            return 0
        else:
            return usage_error(f"unknown argument {a} (the command comes after --)")
    command = argv[i:]
    if not command:
        return usage_error("no command after --")
    return as_login, cwd, command


def at_fabric(command: list[str], fabric: str) -> list[str]:
    return [fabric + "/" + a[len("@fabric/"):] if a.startswith("@fabric/") else a for a in command]


def restore_signals() -> None:
    # Python starts with SIGPIPE and SIGXFSZ ignored, and an exec'd program
    # inherits that; the shell's exec never did (a `yes | head` in the
    # command would die of EPIPE noise instead of quietly).
    for name in ("SIGPIPE", "SIGXFSZ"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), signal.SIG_DFL)


def exec_or_say(argv: list[str], who: str = "worker") -> int:
    """Replace this process by `argv`; only a failure returns, with the exit
    status the shell's exec gave it."""
    restore_signals()
    try:
        os.execvp(argv[0], argv)
    except FileNotFoundError:
        print(f"{who}: {argv[0]}: command not found", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"{who}: {argv[0]}: Permission denied", file=sys.stderr)
        return 126
    except OSError as e:
        print(f"{who}: {argv[0]}: {e.strerror or e}", file=sys.stderr)
        return 126


def account_home(login: str) -> str:
    """The passwd entry's home, from `getent` (a test puts a fake first on
    PATH), or '' when the login is unknown here."""
    try:
        r = subprocess.run(["getent", "passwd", login], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    fields = r.stdout.split("\n", 1)[0].split(":")
    return fields[5] if len(fields) > 5 else ""


def main(argv: list[str]) -> int:
    parsed = parse(argv)
    if isinstance(parsed, int):
        return parsed
    as_login, cwd, command = parsed
    me = pwd.getpwuid(os.geteuid()).pw_name
    if not as_login or as_login == me:
        command = at_fabric(command, ROOT)
        if cwd:
            try:
                os.chdir(cwd)
            except OSError as e:
                print(f"worker: cd {cwd}: {e.strerror}", file=sys.stderr)
                return 1
        return exec_or_say(command)
    home = account_home(as_login)
    if not home:
        return usage_error(f"no such login on {short_hostname()}: {as_login}")
    fabric = f"{home}/projects/agent-fabric"
    needs_fabric = any(a.startswith("@fabric/") for a in command)
    command = at_fabric(command, fabric)
    sudo = (os.environ.get("SUDO") or "sudo").split()
    path = f"/usr/local/bin:/usr/bin:/bin:{home}/.local/bin"
    # AGENT_FABRIC_PATH carries the same PATH for a command that opens a LOGIN
    # shell (bash -l): Debian's /etc/profile assigns PATH outright for a
    # non-root login, so the value set here would be gone by the time the
    # command runs; the command restores it with
    # `export PATH="$AGENT_FABRIC_PATH:$PATH"`.
    return exec_or_say([*sudo, "-n", "-u", as_login, "-H", "env", "-i", f"HOME={home}", f"PATH={path}",
                        f"AGENT_FABRIC_PATH={path}", "bash", "-c", ACCOUNT_STUB, "--",
                        "1" if needs_fabric else "0", fabric, cwd, *command])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
