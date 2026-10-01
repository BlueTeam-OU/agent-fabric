#!/usr/bin/env python3
"""moveto — open a shell as another role account, in its workspace
(~/projects — where a session is launched from), or in a named clone
(ADR-040 Wave 5). runtime/provisioning/moveto/moveto is its shim; install.sh
copies both to /usr/local (the shim to bin/, this file beside enter and rc
in share/moveto/), so this file imports nothing from the fabric: an
installed copy runs with no checkout behind it.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none, -h or --help: USAGE on stdout, exit 0.
            --list: one line per account (uid 1000-65533, in `sort`'s
            order) that has at least one clone: account, role, clones.
            <account> [<clone>] [--print] [--list], options in any order
            after the account; --list there prints that account's clones,
            one per line, and stops; an unknown option, a second clone or
            a clone that is not one path segment: exit 1.
  stdin     never read; the entered shell inherits it.
  env       PATH (getent, sudo, find, test, cat and sort are found there,
            as the bash found them — the suite's mocks rely on it);
            _MOVETO_PIPE_IGNORED, set by the shim when SIGPIPE was ignored
            on entry, and removed before the shell is entered.
  signals   the entered shell gets SIGPIPE as the caller gave it to the
            shim, as the bash's exec passed it on: Python ignores it at
            start-up, and an exec keeps an ignored signal ignored.
  stdout    USAGE, the --list lines, or --print's path and `title: …`.
  stderr    `moveto: …` for a refusal, and one line naming the account and
            directory before the shell is entered.
  exit      0; 1 for every refusal; otherwise the entered shell's (exec).
Names that reach the terminal pass display_safe() at every point they are
displayed; a path that is used keeps the raw name.

Deliberate differences from the bash: display_safe strips what a UTF-8
locale calls a control (C0, DEL, C1, U+2028/U+2029) whatever the locale,
where bash in the C locale stripped C0 and DEL only; every command it runs
is bounded (TIMEOUT_S), and one that runs out reads as that command failing.

Sudo on this host is granted through the `qubes` group, which the role
accounts are NOT in. So this works FROM an account with sudo (`user`)
TO a role account, and not the other way: `exit` is the way back.

A process cannot change its parent's user or directory, so this spawns a
new shell rather than moving the one you typed in.
"""
from __future__ import annotations

import os
import pwd
import re
import signal
import subprocess
import sys
import unicodedata

PROJECTS_SUBDIR = "projects"
CONTROL_PLANE_DIR = "agent-fabric"
MOVETO_ENTER = "/usr/local/share/moveto/enter"
PIPE_IGNORED_ENV = "_MOVETO_PIPE_IGNORED"
# getent, sudo -n, find over one directory: nothing here should take long,
# and a hung directory service must not leave the caller at a dead prompt.
TIMEOUT_S = 60

USAGE = """\
usage: moveto <account>             open a shell as <account>, in its workspace
                                   (~/projects: the place a session launches from)
       moveto <account> <clone>     …in that clone (~/projects/<clone>) instead
       moveto <account> --print     print the resolved path, spawn nothing
       moveto --list                accounts that have at least one clone: account, role, clones
       moveto <account> --list      that account's clones

Sudo here comes from the `qubes` group and role accounts are not in it, so
this runs from an account that has sudo (`user`). From a role account, `exit`
returns to the shell you came from.
"""
ROLE_LINE = re.compile(r'.*"role": *"([^"]*)".*')


class Refused(Exception):
    """`moveto: <message>`, exit 1."""


def die(msg: str) -> "NoReturn":  # noqa: F821
    raise Refused(msg)


def me() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def command(args: list[str], *, stdin: bytes | None = None) -> tuple[int, bytes]:
    """A command's status and stdout; stderr dropped, as every call here
    sent it to /dev/null."""
    try:
        r = subprocess.run(args, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return 127, b""
    return r.returncode, r.stdout


def text(b: bytes) -> str:
    return b.decode("utf-8", "surrogateescape")


def home_of(account: str) -> str:
    rc, out = command(["getent", "passwd", account])
    fields = text(out).rstrip("\n").split("\n")[0].split(":") if rc == 0 else []
    return fields[5] if len(fields) > 5 else ""


# Run a command as an account. The target's own privileges are what is needed
# to read the target's home — not root's — so this binds the tool to
# run-as-target sudo rather than to full root, and a symlink planted in a
# target-writable ~/projects is followed as that account, not as root.
def run_as(account: str, *args: str) -> tuple[int, bytes]:
    if account == me():
        return command(list(args))
    return command(["sudo", "-n", "-u", account, *args])


# Names reach the caller's terminal — via --list, the ambiguity listing, and
# the title — from an account the caller is not yet running as. A filename may
# contain any byte but / and NUL, so ESC is legal, and an OSC string closed
# early by an embedded BEL leaves the rest to be parsed as terminal input.
# Strip control characters at every point a name is DISPLAYED. Path use keeps
# the raw name. /etc/profile.d/vte.sh does the same to $PWD, for this reason.
def display_safe(s: str) -> str:
    return "".join(c for c in s if unicodedata.category(c) != "Cc" and c not in "\u2028\u2029")


def sort_z(items: list[bytes]) -> list[bytes]:
    """In `sort -z`'s order: the locale's collation, as the bash had it."""
    if not items:
        return []
    rc, out = command(["sort", "-z"], stdin=b"\0".join(items) + b"\0")
    return [i for i in out.split(b"\0") if i] if rc == 0 else sorted(items)


# Enumerate an account's clones. NUL-separated rather than `ls`: names may
# contain spaces and newlines, and a newline through a pipe cannot be told from
# a separator. The state says why the list is empty, because "never
# provisioned", "cannot read" and "no clone yet" need different answers.
def list_clones(account: str) -> tuple[list[str], str] | None:
    """(clones, state), or None for no such account."""
    home = home_of(account)
    if not home:
        return None
    projects = f"{home}/{PROJECTS_SUBDIR}"
    if run_as(account, "test", "-e", projects)[0] != 0:
        return [], "no-projects-dir"
    # A clone is a DIRECTORY, and not the control plane: ~/projects also
    # holds the workspace CLAUDE.md that bootstrap.sh writes and the
    # agent-fabric checkout beside the clones, and neither is a place to
    # work a project from.
    _, out = run_as(account, "find", projects, "-mindepth", "1", "-maxdepth", "1", "-type", "d", "!", "-name", ".*",
                    "!", "-name", CONTROL_PLANE_DIR, "-print0")
    clones = [text(e).rsplit("/", 1)[-1] for e in sort_z([e for e in out.split(b"\0") if e])]
    return clones, "" if clones else "empty"


# The role an account holds is in its own binding, bound from a login shell
# (bin/fabric-role) and readable only as the account — so it is read the
# way the clones are, through run_as. "-" when none is bound or readable.
def role_of(account: str) -> str:
    home = home_of(account)
    if not home:
        return "-"
    _, out = run_as(account, "cat", f"{home}/.local/state/agent-fabric/agents/{account}/binding.json")
    for line in text(out).split("\n"):
        m = ROLE_LINE.match(line)
        if m:
            return display_safe(m.group(1) or "-")
    return "-"


# The window title is the ROLE INSTANCE — the account — because that is what
# names a session here. Entering a named clone in an account that holds
# several is the exception: its own name cannot tell two of them apart, so
# the clone name is used.
def title_for(path: str, projects: str, account: str, clones: list[str]) -> str:
    if path != projects and len(clones) > 1:
        return display_safe(path.rsplit("/", 1)[-1])
    return display_safe(account)


def pad(s: str, width: int) -> str:
    """printf's %-<width>s: padded by bytes, as bash's printf counts."""
    return s + " " * max(0, width - len(s.encode("utf-8", "surrogateescape")))


def list_all() -> None:
    rc, out = command(["getent", "passwd"])
    users = []
    for line in text(out).split("\n"):
        f = line.split(":")
        if len(f) > 2 and re.fullmatch(r"-?\d+", f[2]) and 1000 <= int(f[2]) < 65534 and f[0]:
            users.append(f[0].encode("utf-8", "surrogateescape"))
    for u in (text(b) for b in sort_z(users)):
        listed = list_clones(u)
        if listed is None or not listed[0]:
            continue
        line = " ".join(display_safe(c) for c in listed[0])
        print(f"{pad(u, 24)} {pad(role_of(u), 20)} {line}")


def moveto(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if argv[0] == "--list":
        list_all()
        return 0
    account, target, print_only = argv[0], "", False
    for a in argv[1:]:
        if a == "--print":
            print_only = True
        elif a == "--list":
            listed = list_clones(account)
            if listed is None:
                die(f"no such account: {account}")
            for c in listed[0]:
                print(display_safe(c))
            return 0
        elif a.startswith("-"):
            die(f"unknown option '{a}' (try --help)")
        else:
            if target:
                die("one clone at a time")
            # A single path segment. Without this, `moveto acct ../../etc`
            # resolves and lands you outside ~/projects entirely.
            if "/" in a or a in (".", ".."):
                die(f"clone must be a single name under ~/projects, not a path: {a}")
            target = a

    if command(["getent", "passwd", account])[0] != 0:
        die(f"no such account: {account}")
    if account != me() and command(["sudo", "-n", "-u", account, "true"])[0] != 0:
        die(f"cannot become '{account}' without a password. Role accounts are not in the `qubes` group and have no "
            "sudo; run this from an account that does.")

    projects = f"{home_of(account)}/{PROJECTS_SUBDIR}"
    clones, state = list_clones(account) or ([], "")
    # The destination is the WORKSPACE, ~/projects: the directory a session is
    # launched from (bootstrap writes its CLAUDE.md and hooks there; the
    # session-start hook records whichever clone the session then enters), so a
    # shell lands where `claude` would be started, not inside one clone. A named
    # clone is the explicit exception. An account with no projects/ at all is
    # not provisioned, and that is a different answer from an empty one.
    if state == "no-projects-dir":
        die(f"{account} has no {PROJECTS_SUBDIR} directory — not provisioned yet. See the deployment's provisioning "
            "runbook.")
    path = f"{projects}/{target}" if target else projects
    # Verify as the target user: root can stat what the target may not, and the
    # reverse is the failure that would strand you in a shell with no cwd.
    if run_as(account, "test", "-d", path)[0] != 0:
        die(f"no such directory for {account}: {display_safe(path)}")
    title = title_for(path, projects, account, clones)
    if print_only:
        print(display_safe(path))
        print(f"title: {title}")
        return 0

    print(f"moveto: {account} in {path}  (exit returns here)", file=sys.stderr, flush=True)
    sys.stdout.flush()
    # The title travels as an argument, not an export: sudo resets the
    # environment, so an exported value would not cross the boundary.
    #
    # The entering shell is a separate script rather than an inline `bash -lc`,
    # so the process command line stays short. A terminal that titles from the
    # running command showed the whole inline script otherwise.
    enter(account, path, title)


def enter(account: str, path: str, title: str) -> "NoReturn":  # noqa: F821
    pipe = signal.SIG_IGN if os.environ.pop(PIPE_IGNORED_ENV, "") == "1" else signal.SIG_DFL
    signal.signal(signal.SIGPIPE, pipe)
    if account == me():
        os.execv(MOVETO_ENTER, [MOVETO_ENTER, path, title])
    os.execvp("sudo", ["sudo", "-n", "-u", account, "-H", MOVETO_ENTER, path, title])


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    # BrokenPipeError is an OSError: it is caught first, and stdout is
    # flushed inside the try, so a reader that went away is exit 141, not
    # an exec failure or an error at interpreter shutdown.
    try:
        rc = moveto(argv)
        sys.stdout.flush()
        return rc
    except Refused as exc:
        print(f"moveto: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except OSError as exc:
        print(f"moveto: {exc.filename or MOVETO_ENTER}: {exc.strerror or exc}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
