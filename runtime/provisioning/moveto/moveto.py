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
            order) whose projects/ holds a clone or the control-plane
            checkout: account, role, then what projects/ holds, agent-fabric
            included (it is no clone to enter: `moveto <account> --list`
            does not name it).
            <account> [<clone>] [--print] [--list] [--wait|--resume|--watch],
            options in any order after the account; --list there prints
            that account's clones, one per line, and stops; an unknown
            option, a second clone, a clone that is not one path segment,
            two different modes, a --via that is neither ssh nor sudo, or
            two different --via: exit 1. A mode is handed to enter as
            its last argument, a fixed word (Fleet Deck reads it there).
            --via ssh|sudo (also --via=ssh) says how the account is entered
            (ADR-048). ssh: `ssh -i ~/.ssh/fabric_deck -o IdentitiesOnly=yes
            -o UserKnownHostsFile=<generated> -o StrictHostKeyChecking=yes
            [-p <port>] -t <account>@<address> -- <word>`, the word one of
            --wait|--watch|--resume|shell (shell for no mode), which the
            account's forced command (enter-ssh) runs `enter` for: the
            workspace only, so a named clone is refused; no sudo is needed.
            sudo: the break-glass, unchanged. Without --via: ssh when the
            account's host has a pinned sshd in the registry, else sudo
            (`fabric-host ssh-pin`; no fabric-host on the PATH, or an older
            one with no ssh-pin, is sudo, said in the second case; a
            registry it cannot read is a refusal). known_hosts is
            `fabric-ssh-hosts known-hosts`, written whole to
            $XDG_STATE_HOME/fabric-deck/known_hosts (0600) at every entry.
  stdin     never read; the entered shell inherits it.
  env       PATH (also fabric-host, fabric-ssh-hosts and ssh for --via; HOME and
            XDG_STATE_HOME for the key and the known_hosts) (getent, sudo, find, test, cat and sort are found there,
            as the bash found them — the suite's mocks rely on it);
            _MOVETO_PIPE_IGNORED, set by the shim when SIGPIPE was ignored
            on entry, and removed before the shell is entered.
  signals   the entered shell gets SIGPIPE as the caller gave it to the
            shim, as the bash's exec passed it on: Python ignores it at
            start-up, and an exec keeps an ignored signal ignored.
  stdout    USAGE, the --list lines, or --print's path, `title: …` and,
            with a mode, `then: …` (and `via: ssh` when it would go by ssh).
  stderr    `moveto: …` for a refusal, and one line naming the account (and,
            by sudo, the directory) before the shell is entered.
  exit      0; 1 for every refusal; otherwise the entered shell's (exec).
Names that reach the terminal pass display_safe() at every point they are
displayed; a path that is used keeps the raw name.

Deliberate differences from the bash: display_safe strips what a UTF-8
locale calls a control (C0, DEL, C1, U+2028/U+2029) whatever the locale,
where bash in the C locale stripped C0 and DEL only; every command it runs
is bounded (TIMEOUT_S), and one that runs out reads as that command failing.

ENTER (`moveto.py --enter <dir> <title> [--wait|--resume|--watch]`, run by
the stub `enter` that moveto hands off to, under a login shell): the account's
side of the entry, ported from the bash `enter`. argv is exactly that, the mode
a fixed word and always last (Fleet Deck reads it from the `sudo … enter`
hand-off). It sets the tab title, waits for one Enter under --wait, refreshes
the account (fast-forward agent-fabric, bootstrap, the secrets: each best
effort, a problem said in one line, the shell still opens), runs fabric-resume
or fabric-watch for the mode, and becomes `bash --rcfile …/rc -i`. exit 1 when
<dir> cannot be entered, 2 for a missing argument; otherwise the shell's.
`--enter` first is the only argument this adds; no account can be named so.

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
import tempfile
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
       moveto <account> --resume    …and resume its last session there (fabric-resume),
                                   or start a fresh one and say so; the shell follows
       moveto <account> --wait      …say "<account> - Enter to activate", then on Enter
                                   refresh and do exactly --resume; end of input: a shell
       moveto <account> --watch     …and show its status (fabric-watch) until q; the shell follows
       moveto <account> --print     print the resolved path, spawn nothing
       moveto <account> --via ssh   …through the pinned sshd (ADR-048: the account's forced command enters it;
                                   the workspace only, no clone) instead of sudo; --via sudo is the break-glass.
                                   Without --via: ssh when the account's host has a pinned sshd, else sudo
       moveto --list                accounts with a clone or the agent-fabric checkout: account, role, what ~/projects holds
       moveto <account> --list      that account's clones

Sudo here comes from the `qubes` group and role accounts are not in it, so
this runs from an account that has sudo (`user`). From a role account, `exit`
returns to the shell you came from.
"""
# The operator's key and the file ssh trusts hosts from (ADR-048 §5 rules 3 and 5): the key is made once by the
# owner; known_hosts is regenerated from the registry at every entry, never edited, never keyscanned.
SSH_KEY = "~/.ssh/fabric_deck"
VIA_WORDS = ("ssh", "sudo")
# What each mode has enter do, as --print says it.
MODES = {"--wait": "Enter to activate, then fabric-resume", "--resume": "fabric-resume", "--watch": "fabric-watch"}
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
def list_clones(account: str, control_plane: bool = False) -> tuple[list[str], str] | None:
    """(clones, state), or None for no such account. `control_plane` counts the
    agent-fabric checkout among them: for `moveto --list`, which says which accounts
    exist and Fleet Deck makes a tab of; never for naming a clone to enter."""
    home = home_of(account)
    if not home:
        return None
    projects = f"{home}/{PROJECTS_SUBDIR}"
    if run_as(account, "test", "-e", projects)[0] != 0:
        return [], "no-projects-dir"
    # A clone is a DIRECTORY, and not the control plane: ~/projects also
    # holds the workspace CLAUDE.md that bootstrap.sh writes and the
    # agent-fabric checkout beside the clones, and neither is a place to
    # work a project from. `control_plane` is for `moveto --list` alone, which
    # names the checkout so that an account holding nothing else is listed.
    skip = [] if control_plane else ["!", "-name", CONTROL_PLANE_DIR]
    _, out = run_as(account, "find", projects, "-mindepth", "1", "-maxdepth", "1", "-type", "d", "!", "-name", ".*",
                    *skip, "-print0")
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
        # An account whose projects/ holds only the control-plane checkout is listed, with
        # agent-fabric among its clones: python-dev-01 holds nothing else, and Fleet Deck
        # builds no tab for an account this leaves out. One with no projects/, or nothing in it, stays out.
        listed = list_clones(u, control_plane=True)
        if listed is None or not listed[0]:
            continue
        line = " ".join(display_safe(c) for c in listed[0])
        print(f"{pad(u, 24)} {pad(role_of(u), 20)} {line}")


class PinUnknown(Exception):
    """fabric-host has no ssh-pin: a checkout older than this moveto. It cannot say, which is not "no pin"."""


def ssh_pin(account: str) -> tuple[str, int] | None:
    """(address, port) of the pinned sshd of the host `account` is placed on, or None when the registry has none
    (`fabric-host ssh-pin`, which reads the registry as every fabric tool does). A registry that cannot be read is an
    error, said: the default is sudo only where the registry says there is no pin, not where it could not be asked;
    PinUnknown where fabric-host cannot answer at all (usage status 2)."""
    try:
        r = subprocess.run(["fabric-host", "ssh-pin", account], capture_output=True, text=True, timeout=TIMEOUT_S,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return None    # no fabric-host on this PATH: a machine with no registry to ask, which has only ever had sudo
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"cannot ask fabric-host which way to enter {account} ({exc.__class__.__name__}); --via sudo does not need it") from None
    words = r.stdout.split()
    if r.returncode == 2:
        raise PinUnknown
    if r.returncode != 0:
        why = display_safe((r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1][:160])
        raise Refused(f"cannot read the registry's ssh pin for {account} ({why}); --via sudo does not need it")
    if words == ["sudo"]:
        return None
    if len(words) == 3 and words[0] == "ssh" and words[2].isdigit():
        return words[1], int(words[2])
    raise Refused(f"fabric-host ssh-pin answered something moveto cannot read: {display_safe(r.stdout.strip()[:80])}")


def known_hosts_file() -> str:
    """The generated known_hosts, replaced whole at every entry from `fabric-ssh-hosts known-hosts`; its path.
    Under the state directory, private to this account: ssh is exec'd and cannot clean up behind itself."""
    try:
        r = subprocess.run(["fabric-ssh-hosts", "known-hosts"], capture_output=True, text=True, timeout=TIMEOUT_S,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"cannot run fabric-ssh-hosts known-hosts ({exc.__class__.__name__}); --via sudo does not need it") from None
    if r.returncode != 0 or not r.stdout.strip():
        why = display_safe((r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1][:160])
        raise Refused(f"no known_hosts from the registry ({why}); --via sudo does not need it")
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    directory = os.path.join(state, "fabric-deck")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="known_hosts.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(r.stdout if r.stdout.endswith("\n") else r.stdout + "\n")
        os.replace(tmp, os.path.join(directory, "known_hosts"))
    except BaseException:
        os.unlink(tmp)
        raise
    return os.path.join(directory, "known_hosts")


def ssh_argv(account: str, mode: str, pin: tuple[str, int], known_hosts: str, key: str) -> list[str]:
    """The ssh command that enters `account` (ADR-048 §5 rule 4): the forced command takes one of four exact words,
    `shell` for none. The word follows `--`: OpenSSH reads options after the destination too, and a bare --wait is
    `unknown option -- -` (ssh 10.0)."""
    address, port = pin
    return ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "StrictHostKeyChecking=yes", *(["-p", str(port)] if port != 22 else []), "-t",
            f"{account}@{address}", "--", mode or "shell"]


def enter_over_ssh(account: str, target: str, print_only: bool, mode: str, pin: tuple[str, int]) -> int:
    """Enter `account` through its pinned sshd: the forced command (enter-ssh) runs enter in the workspace, so a named
    clone cannot be asked for, and nothing here needs sudo. Same words on --print as the sudo path, plus `via: ssh`."""
    if target:
        die("over ssh the account is entered in its workspace only (enter-ssh runs enter there); a named clone needs --via sudo")
    path = f"{home_of(account)}/{PROJECTS_SUBDIR}"
    if print_only:
        print(display_safe(path))
        print(f"title: {display_safe(account)}")
        if mode:
            print(f"then: {MODES[mode]}")
        print("via: ssh")
        return 0
    key = os.path.expanduser(SSH_KEY)
    if not os.path.isfile(key):
        die(f"no operator key at {SSH_KEY} (ADR-048 §5 rule 3: the owner makes it with ssh-keygen); --via sudo does not need it")
    argv = ssh_argv(account, mode, pin, known_hosts_file(), key)
    print(f"moveto: {account} over ssh  (exit returns here)", file=sys.stderr, flush=True)
    sys.stdout.flush()
    signal.signal(signal.SIGPIPE, signal.SIG_IGN if os.environ.pop(PIPE_IGNORED_ENV, "") == "1" else signal.SIG_DFL)
    os.execvp(argv[0], argv)


def moveto(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if argv[0] == "--list":
        list_all()
        return 0
    account, target, print_only, mode, via = argv[0], "", False, "", ""
    rest = iter(argv[1:])
    for a in rest:
        if a == "--print":
            print_only = True
        elif a == "--via" or a.startswith("--via="):
            value = a.split("=", 1)[1] if "=" in a else next(rest, "")
            if value not in VIA_WORDS:
                die(f"--via takes ssh or sudo, not '{display_safe(value)}'")
            if via and via != value:
                die("one of --via ssh, --via sudo")
            via = value
        elif a in MODES:
            # Fleet Deck's modes (architect-cto's plan, 2026-10-07;
            # docs/fleet-deck/tab-states.md): the account's own tools do
            # the work; moveto only tells enter which, and gains no
            # privilege. One pane does one thing.
            if mode and mode != a:
                die(f"one of {', '.join(MODES)} at a time")
            mode = a
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
    pin = None
    if account == me():
        if via == "ssh":
            die("--via ssh enters another account; this one is entered directly (leave --via out)")
    elif via != "sudo" and not (via == "" and target):
        # A named clone is sudo's to enter: enter-ssh enters the workspace only. Asked for with --via ssh it is refused below.
        try:
            pin = ssh_pin(account)
        except PinUnknown:
            if via == "ssh":
                die("this fabric-host has no ssh-pin (an older checkout), so --via ssh cannot be served; --via sudo enters without it")
            # sudo is what an older checkout has always meant; said, so a mis-deployment is not mistaken for "no pin".
            print("moveto: this fabric-host has no ssh-pin (an older checkout); entering through sudo", file=sys.stderr)
    if via == "ssh" and pin is None:
        die(f"no pinned sshd for {account}'s host in the registry (hosts.<host>.sshd with host_keys), or no fabric-host to read it; "
            "--via sudo enters without it")
    if pin is not None:
        return enter_over_ssh(account, target, print_only, mode, pin)
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
        if mode:
            print(f"then: {MODES[mode]}")
        return 0

    print(f"moveto: {account} in {path}  (exit returns here)", file=sys.stderr, flush=True)
    sys.stdout.flush()
    # The title travels as an argument, not an export: sudo resets the
    # environment, so an exported value would not cross the boundary.
    #
    # The entering shell is a separate script rather than an inline `bash -lc`,
    # so the process command line stays short. A terminal that titles from the
    # running command showed the whole inline script otherwise.
    enter(account, path, title, mode)


def enter(account: str, path: str, title: str, mode: str = "") -> "NoReturn":  # noqa: F821
    pipe = signal.SIG_IGN if os.environ.pop(PIPE_IGNORED_ENV, "") == "1" else signal.SIG_DFL
    signal.signal(signal.SIGPIPE, pipe)
    tail = [mode] if mode in MODES else []
    if account == me():
        os.execv(MOVETO_ENTER, [MOVETO_ENTER, path, title, *tail])
    os.execvp("sudo", ["sudo", "-n", "-u", account, "-H", MOVETO_ENTER, path, title, *tail])


ENTER_RC = "/usr/local/share/moveto/rc"
PULL_TIMEOUT_S, BOOTSTRAP_TIMEOUT_S, SECRETS_TIMEOUT_S = 30, 30, 20


def run_bounded(argv: list[str], timeout: int, *, capture: bool = False, quiet: bool = False, merge: bool = True) -> tuple[int, str]:
    """(status, the text when `capture`) of a command in a group of
    its own, killed with its children when it runs out: status 124, as the
    coreutils `timeout` said it. A command that cannot start is 127. With
    `capture`, stderr is merged into the text unless `merge` is off (then it
    is discarded: a git warning must not be read as git's answer)."""
    out = subprocess.PIPE if capture else (subprocess.DEVNULL if quiet else None)
    try:
        proc = subprocess.Popen(argv, stdin=None, stdout=out, stderr=(subprocess.STDOUT if merge else subprocess.DEVNULL) if capture else (subprocess.DEVNULL if quiet else None),
                                text=True, errors="replace", start_new_session=True)
    except OSError:
        return 127, ""
    try:
        text, _ = proc.communicate(timeout=timeout)
        return proc.returncode, text or ""
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            try:
                text, _ = proc.communicate(timeout=5)
                return 124, text or ""
            except subprocess.TimeoutExpired:
                continue
        return 124, ""


def pull_reason(output: str, rc: int) -> str:
    """git's first error line names the cause ("ssh: Could not resolve
    hostname", "fatal: Not possible to fast-forward"); its last is often
    boilerplate. A hung network writes nothing before the timeout: then the
    status says it."""
    for line in output.splitlines():
        if line.startswith(("fatal:", "error:", "ssh:")):
            return line
    last = output.rstrip("\n").rsplit("\n", 1)[-1]
    if last:
        return last
    return "git pull timed out after 30 s" if rc == 124 else f"git pull exit {rc}"


def refresh_fabric(fabric: str) -> None:
    """Entering an account is its refresh point. Three things, each best effort
    — offline or unenrolled, what is there stands, the shell still opens, and
    only a problem is worth one line: the control plane (agent-fabric is
    read-only for every role but the coordinator, so this clone can only be
    behind — fast-forward it); bootstrap, which installs from that checkout and
    is idempotent; the account's secrets, from its own store, before the shell
    sources them."""
    rc, inside = run_bounded(["git", "-C", fabric, "rev-parse", "--is-inside-work-tree"], TIMEOUT_S, capture=True, merge=False)
    if rc == 0 and inside.strip() == "true":
        rc, pulled = run_bounded(["git", "-C", fabric, "pull", "-q", "--ff-only", "origin", "main"], PULL_TIMEOUT_S, capture=True)
        if rc != 0:
            print(f"moveto: agent-fabric not fast-forwarded ({pull_reason(pulled, rc)}); using it as is", file=sys.stderr)
        else:
            # --ff-only succeeds without a word on a clone that is AHEAD of
            # origin/main, so commits nobody merged stayed in force unsaid
            # (review of #80). A count git cannot give is said as unknown,
            # never read as zero.
            code, counted = run_bounded(["git", "-C", fabric, "rev-list", "--count", "origin/main..HEAD"], TIMEOUT_S, capture=True, merge=False)
            ahead = counted.strip() if code == 0 else ""
            if not ahead.isascii() or not ahead.isdigit():
                print("moveto: agent-fabric's commits beyond origin/main are unknown; using it as is", file=sys.stderr)
            elif ahead != "0":
                print(f"moveto: agent-fabric is {ahead} commit(s) ahead of origin/main, which only a merge changes; using it as is", file=sys.stderr)
        rc, _ = run_bounded(["bash", os.path.join(fabric, "runtime", "claude-code", "bootstrap.sh")], BOOTSTRAP_TIMEOUT_S, quiet=True)
        if rc != 0:
            print("moveto: bootstrap did not complete; run it by hand", file=sys.stderr)
    secrets = os.path.join(fabric, "bin", "fabric-secrets")
    if os.access(secrets, os.X_OK):
        run_bounded([secrets, "sync", "--quiet"], SECRETS_TIMEOUT_S)    # best effort: its status is not the entry's


def read_line_unbuffered(fd: int) -> bytes:
    """One line from `fd` a byte at a time, as the shell's `read -r` reads a pipe: nothing past
    the newline is taken from the shell that follows. b'' or a partial line is end of input."""
    out = b""
    while True:
        try:
            c = os.read(fd, 1)
        except InterruptedError:
            continue
        if not c:
            return out
        out += c
        if c == b"\n":
            return out


def enter_main(argv: list[str]) -> int:
    if not argv:
        print("moveto: enter needs <dir> <title> [mode]", file=sys.stderr)
        return 2
    directory, title = argv[0], argv[1] if len(argv) > 1 else ""
    mode = argv[2] if len(argv) > 2 else ""
    try:
        os.chdir(directory)
    except OSError as exc:
        print(f"moveto: cd {directory}: {exc.strerror}", file=sys.stderr)
        return 1
    os.environ["MOVETO_TITLE"] = title
    if mode not in ("", *MODES):
        print(f"moveto: unknown mode '{mode}'; a plain shell", file=sys.stderr)
        mode = ""
    # Set the title NOW, before the refresh and before any wait: a pane armed
    # --wait sits here, and PROMPT_COMMAND alone would leave the terminal
    # showing whatever it had while this was starting up. OSC 1 = icon/tab
    # name, OSC 2 = window title. Explicit beats OSC 0, which means "both" and
    # is honoured inconsistently.
    sys.stdout.write(f"\033]1;{title}\007\033]2;{title}\007")
    # --wait (Fleet Deck's dormant pane): one line, then one Enter does exactly
    # --resume. The line comes BEFORE the refresh, so the pull, the bootstrap
    # and the secrets are as fresh as the Enter, not as the pane. The line
    # read is discarded whatever it holds; input that ends first is a plain
    # shell, said.
    if mode == "--wait":
        sys.stdout.write(f"{me()} - Enter to activate\n")
        sys.stdout.flush()
        if read_line_unbuffered(0).endswith(b"\n"):
            mode = "--resume"
        else:
            print("moveto: input ended before Enter; a plain shell, nothing activated", file=sys.stderr)
            mode = ""
    # From here: Ctrl-C while the account refreshes or its tool runs is the tool's (fabric-watch quits on
    # it), never the entry's: the bash carried on to the shell when a foreground child took the
    # SIGINT. A Python handler, not SIG_IGN: it is reset to the default in every child.
    if signal.getsignal(signal.SIGINT) is not signal.SIG_IGN:    # an inherited ignore stays one, in the children too
        signal.signal(signal.SIGINT, lambda *_: None)
    sys.stdout.flush()
    fabric = os.path.join(os.environ.get("HOME", ""), "projects", "agent-fabric")
    refresh_fabric(fabric)
    # --resume (Fleet Deck's re-entry): the account's last session comes back
    # first, as a child of this shell's start, through its own launcher
    # (bin/fabric-resume), which says when it starts fresh instead, and
    # refuses when a session already runs; when that session ends, the shell
    # follows. --watch (the deck's status pane): bin/fabric-watch, read-only,
    # until q; then the account's shell. A checkout older than either (its pull
    # failed): the pane says nothing ran, never a silent plain shell.
    tool = {"--resume": "fabric-resume", "--watch": "fabric-watch"}.get(mode, "")
    path = os.path.join(fabric, "bin", tool)
    if tool and os.access(path, os.X_OK):
        try:
            status = subprocess.run([path], timeout=None).returncode
        except OSError:
            status = 126
        if status != 0:
            print(f"moveto: {tool} exited {128 - status if status < 0 else status}", file=sys.stderr)   # the shell's $?
    elif tool:
        print(f"moveto: no {tool} in {fabric}; nothing run", file=sys.stderr)
    sys.stderr.flush()
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)      # SIGINT's Python handler is reset by the exec itself
    os.execvp("bash", ["bash", "--rcfile", ENTER_RC, "-i"])


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    # BrokenPipeError is an OSError: it is caught first, and stdout is
    # flushed inside the try, so a reader that went away is exit 141, not
    # an exec failure or an error at interpreter shutdown.
    try:
        rc = enter_main(argv[1:]) if argv[:1] == ["--enter"] else moveto(argv)
        sys.stdout.flush()
        return rc
    except Refused as exc:
        print(f"moveto: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except KeyboardInterrupt:
        return 130      # Ctrl-C at the --wait prompt ends the entry, as it ended the bash script
    except OSError as exc:
        print(f"moveto: {exc.filename or MOVETO_ENTER}: {exc.strerror or exc}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
