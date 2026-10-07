#!/usr/bin/env python3
"""tools/fabric/new_agent_worker.py — the decisions of new-agent's host
half (ADR-040 Wave 5). runtime/provisioning/new-agent-worker.sh stays a
bash step-runner (ADR-040 rule 1: sudo, useradd and the vendors'
installers); what it must decide — its arguments, the claude version, the
subordinate id range, the GitHub host keys an account lacks, the closing
list — it asks this module, by the fleet's pinned interpreter's fixed
path (the worker runs as a host's operator, with sudo: an interpreter the
environment chose could be anything). Standard library only, nothing
imported from the fabric: tests/test_new_agent_cli.py runs it in a fixture fabric.

    new_agent_worker.py args <worker argv…>        the worker's variables, as bash to eval
    new_agent_worker.py host-check <login>         hostname -s, then whether the account exists
    new_agent_worker.py audit <platform> <persists> <hint> <n-tools> [<package>…]
    new_agent_worker.py claude-want <root> [<target>]
    new_agent_worker.py subids <login> <etc>       "have <start>:<count>" or "alloc <start>-<end>"
    new_agent_worker.py missing-keys <keys-file>   known_hosts on stdin; the lines it lacks
    new_agent_worker.py verify <root> <login> <home> <sudo> [--claude-account=<slug>=<fp12> | --no-claude-account]
                               [<project>…]   step 10 and the closing list; exit 1 when the account given is not applied

CONTRACT of the worker, frozen from the bash (ADR-040 §5 rule 3), parsed
here: `prepare|finish <login> <role> [--claude V] [--clone <id>=<remote>]…
[--project <id>]… [--claude-account <slug>=<fp12> | --no-claude-account]
[--dry-run]` or `host-check <login>`; a missing phase:
USAGE, exit 2; an unknown argument, no login, no role: one line, exit 2;
--claude without a value: exit 1. Exactly as the bash shifted: a phase
with too few words keeps them, so `prepare <login>` reports the login as
an unknown argument, not "no role" (replicated, not fixed).
Every message here is the worker's own (`new-agent: …`, or
`new-agent-worker: …` for its usage), on stderr.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time

USAGE = "usage: new-agent-worker.sh prepare|finish <login> <role> ... | host-check <login> [--project <id>]..."
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# Checked again here, whatever the caller checked: the value is spliced
# into the string as_login evals.
TARGET = re.compile(r"stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?")
# The Claude account finish verifies: a template's slug and its token's
# fingerprint (sha256[:12]), as the orchestrator read them from its store.
# Checked here too: the value is spliced into the string the worker evals.
CLAUDE_ACCOUNT = re.compile(r"([a-z0-9][a-z0-9-]{0,62})=([0-9a-f]{12})")


class Exit(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


def args(argv: list[str]) -> str:
    """The worker's variables as bash assignments, every value quoted."""
    phase = argv[0] if argv else ""
    rest = argv[1:]
    login = rest[0] if rest else ""
    role = ""
    if phase in ("prepare", "finish"):
        role = rest[1] if len(rest) > 1 else ""
        # `shift 2 || true`: with fewer than two words bash shifts none.
        rest = rest[2:] if len(rest) >= 2 else rest
    elif phase == "host-check":
        rest = rest[1:] if rest else rest
    else:
        raise Exit(2, USAGE)
    dry, claude, projects, remote, account, no_account = 0, "", [], {}, "", 0
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--dry-run":
            dry = 1
        elif a == "--no-claude-account":
            no_account = 1
        elif a == "--claude-account" or a.startswith("--claude-account="):
            if a == "--claude-account":
                if i + 1 >= len(rest):
                    raise Exit(1, f"new-agent-worker: {a} needs a value")
                i += 1
                account = rest[i]
            else:
                account = a[len("--claude-account="):]
            if not CLAUDE_ACCOUNT.fullmatch(account):
                raise Exit(2, "new-agent-worker: --claude-account takes <slug>=<12 hex of its token's sha256>")
        elif a in ("--claude", "--clone", "--project"):
            if i + 1 >= len(rest):
                raise Exit(1, f"new-agent-worker: {a} needs a value")
            v = rest[i + 1]
            i += 1
            if a == "--claude":
                claude = v
            elif a == "--project":
                projects.append(v)
            else:
                pid = v.split("=", 1)[0]
                remote[pid] = v.split("=", 1)[1] if "=" in v else v
                projects.append(pid)
        elif a.startswith("--claude="):
            claude = a[len("--claude="):]
        elif a.startswith("--clone="):
            v = a[len("--clone="):]
            pid = v.split("=", 1)[0]
            remote[pid] = v.split("=", 1)[1] if "=" in v else v
            projects.append(pid)
        else:
            raise Exit(2, f"new-agent-worker: unknown argument {a}")
        i += 1
    if not login:
        raise Exit(2, "new-agent-worker: no login")
    if phase != "host-check" and not role:
        raise Exit(2, "new-agent-worker: no role")
    if account and no_account:
        raise Exit(2, "new-agent-worker: --claude-account and --no-claude-account together")
    q = shlex.quote
    lines = [f"PHASE={q(phase)}", f"LOGIN={q(login)}", f"ROLE={q(role)}", f"DRY={dry}",
             f"CLAUDE_TARGET={q(claude)}", "PROJECTS=(" + " ".join(q(p) for p in projects) + ")",
             "declare -A REMOTE=(" + " ".join(f"[{q(k)}]={q(v)}" for k, v in remote.items()) + ")",
             # verify's own flags, whole: the step-runner passes them as they are.
             "VERIFY_ACCOUNT=(" + (q(f"--claude-account={account}") if account else
                                   "--no-claude-account" if no_account else "") + ")"]
    return "\n".join(lines) + "\n"


def host_check(login: str) -> str:
    """The host names itself; the coordinator compares this with the
    registry id it reached the host as, and never stamps a host it is not
    on. `hostname -s` and getent as commands, as the bash ran them."""
    name = run_bounded(["hostname", "-s"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       timeout=READBACK_TIMEOUT_S).stdout.decode("utf-8", "surrogateescape")
    present = run_bounded(["getent", "passwd", login], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          timeout=READBACK_TIMEOUT_S).returncode == 0
    return name + ("account: present\n" if present else "account: absent\n")


def audit(platform_id: str, persists: str, hint: str, n_tools: str, packages: list[str]) -> str:
    """Step 0, the host: what the fabric's host contract (platform/detect.sh:
    FABRIC_HOST_TOOLS) finds missing, as the packages that hold it — what
    its hooks, scripts and provisioning call; the package each comes from,
    and where a package persists, is the platform profile's. A Qubes AppVM
    keeps only /home and /usr/local across a reboot, so there a package is
    the TemplateVM's. A project's extra needs are its own host-check."""
    pkgs = " ".join(packages)
    if not packages:
        return f"new-agent: 0. {platform_id}: host tools present ({n_tools}, the fabric's contract)\n"
    try:
        persists_on = int(persists or "0") != 0   # bash's (( … )): a number, empty as 0
    except ValueError:
        persists_on = False
    if persists_on:
        return f"new-agent: 0. {platform_id}: this host lacks {pkgs}: {hint} {pkgs}\n"
    return (f"new-agent: 0. {platform_id}: this AppVM lacks {pkgs} — a package does not survive a reboot here;\n"
            f"new-agent:    {hint} {pkgs}   (then restart this AppVM)\n")


def claude_want(root: str, target: str) -> str:
    """The version the installer is given. claude: the vendor's installer,
    as the account, on the version the fleet pins
    (runtime/claude-code/harness.json — what `fabric-ctl … upgrade claude`
    brings every account to), so a new account starts where the others
    are; --claude overrides it (a version, stable or latest), and with no
    pin readable it is the vendor's latest. The pin reaches as_login's
    eval: a pin that is not a version is refused, and a pin that cannot be
    read is said, never silently turned into latest."""
    try:
        with open(f"{root}/runtime/claude-code/harness.json", encoding="utf-8") as fh:
            pinned = str(json.load(fh).get("claude") or "")
    except (OSError, ValueError, AttributeError):
        pinned = ""
    if pinned and not VERSION.fullmatch(pinned):
        raise Exit(1, f"new-agent: runtime/claude-code/harness.json pins claude '{pinned}', which is not a version; "
                      "nothing installed")
    if not target and not pinned:
        print("new-agent:    claude: no readable pin in runtime/claude-code/harness.json — the vendor's latest instead",
              file=sys.stderr)
    want = target or pinned or "latest"
    if not TARGET.fullmatch(want):
        raise Exit(1, f"new-agent: claude target '{want}' is not stable, latest or a version; nothing installed")
    return want


def subids(login: str, etc: str) -> str:
    """A subordinate uid AND gid range, or rootless podman can unpack no
    image and every Testcontainers suite fails on the login: useradd
    allocates one by default (login.defs SUB_UID_COUNT), but an account
    made another way has none — architect-cto-01 was that account, found
    2026-09-19 with 2716 fixture failures. The next free block above every
    range in the files (SUB_UID_MIN when they are empty), the same block
    for both."""
    def lines(name: str) -> list[str]:
        try:
            with open(f"{etc}/{name}", encoding="utf-8", errors="surrogateescape") as fh:
                return fh.read().splitlines()
        except OSError:
            return []
    uid, gid = lines("subuid"), lines("subgid")
    mine = [ln for ln in uid if ln.startswith(f"{login}:")]
    if mine and any(ln.startswith(f"{login}:") for ln in gid):
        return "have " + mine[0].split(":", 1)[1] + "\n"
    defs = {}
    for ln in lines("login.defs"):
        f = ln.split()
        if len(f) >= 2 and f[0] in ("SUB_UID_MIN", "SUB_UID_COUNT"):
            defs.setdefault(f[0], f[1])
    start = int(defs.get("SUB_UID_MIN") or 524288)
    count = int(defs.get("SUB_UID_COUNT") or 65536)
    for ln in uid + gid:
        f = ln.split(":")
        try:
            start = max(start, int(f[1]) + int(f[2]))
        except (IndexError, ValueError):
            pass
    return f"alloc {start}-{start + count - 1}\n"


def missing_keys(keys_file: str, known_hosts: str) -> str:
    """From the committed copy of GitHub's PUBLISHED keys (github-host-keys,
    api.github.com/meta, fingerprints checked against docs.github.com when
    the file was written — docs/live-checks/2026-09-16-github-host-keys.md),
    never ssh-keyscan: a scan trusts whatever answers on the network the
    bootstrap is about to use (review, 2026-09-16). Every key line the
    account does not hold yet, as a whole line; a changed key at GitHub is
    a change to the committed file, reviewed like any other."""
    have = set(known_hosts.splitlines())
    with open(keys_file, encoding="utf-8") as fh:
        return "".join(f"{ln}\n" for ln in fh.read().splitlines() if ln and ln not in have)


# Each read-back is a question to the account; none should take long, and
# a hung one (a network, a gpg-agent) must not hold the verification.
READBACK_TIMEOUT_S = 120
# A bounded command that runs out is ended with what it started: its direct
# child is sudo, ssh or a bash wrapper, and killing that alone left the rest
# running — an account still being set up after the run said it failed.
# SIGTERM goes to the whole tree first, since sudo relays it to the command
# it runs (SIGKILL it cannot relay, and a process of another account is not
# ours to signal); SIGKILL follows for whatever is left after the grace.
STOP_GRACE_S = 5


def _stat_fields(pid: int) -> list[str] | None:
    """/proc/<pid>/stat after the command name, which may hold spaces and
    parentheses: [state, ppid, ...]; None when the process is gone."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as fh:
            return fh.read().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None


def descendants(pid: int) -> list[int]:
    kids: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            f = _stat_fields(int(entry))
            if f and len(f) > 1 and f[1].isdigit():
                kids.setdefault(int(f[1]), []).append(int(entry))
    found, todo = [], [pid]
    while todo:
        for k in kids.get(todo.pop(), []):
            found.append(k)
            todo.append(k)
    return found


def stop_tree(proc: subprocess.Popen) -> None:
    def alive(pid: int) -> bool:
        f = _stat_fields(pid)
        return bool(f) and f[0] != "Z"

    def reach(pid: int) -> str:
        """Whether a signal reaches it: "ours"; "theirs" for a process of
        another account (root's, under sudo), which no wait makes ours; or
        "gone", exited since it was last seen — kept apart from "theirs", so
        a process that just ended is not named another account's."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "gone"
        except PermissionError:
            return "theirs"
        return "ours"

    def send(pids: list[int], sig: int) -> None:
        for pid in pids:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass

    def running() -> list[int]:
        return [p for p in tree if alive(p) and reach(p) == "ours"]
    tree = [proc.pid, *descendants(proc.pid)]
    send(tree, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_S
    while time.monotonic() < deadline:
        proc.poll()
        tree += [d for d in (descendants(proc.pid) if proc.returncode is None else []) if d not in tree]
        if not running():
            break
        time.sleep(0.05)
    send(running(), signal.SIGKILL)
    proc.wait()
    # SIGKILL is delivered, not yet acted on: a grandchild can still read
    # as running for a moment after it, and "ended" is a claim about the
    # tree, so it is waited for — bounded, and said if the bound passes.
    # Only what a signal reached is waited for; the rest is named as such.
    deadline = time.monotonic() + STOP_GRACE_S
    while running():
        if time.monotonic() >= deadline:
            left = " ".join(str(p) for p in running())
            print(f"new-agent:    {proc.args[0]}: still running after SIGKILL: pid {left}", file=sys.stderr)
            break
        time.sleep(0.02)
    unreached = " ".join(str(p) for p in tree if alive(p) and reach(p) == "theirs")
    if unreached:
        print(f"new-agent:    {proc.args[0]}: could not be signalled (another account's): pid {unreached}", file=sys.stderr)


def run_bounded(cmd: list[str], *, timeout: float, **popen) -> subprocess.CompletedProcess:
    """subprocess.run(cmd, timeout=…), the timeout ending the command's
    whole process tree (stop_tree) before TimeoutExpired is raised. The
    exception carries the bound the call was given: before 3.13, the one
    communicate() raises holds what was left of it."""
    with subprocess.Popen(cmd, **popen) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(proc)
            raise subprocess.TimeoutExpired(cmd, timeout) from None
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


class Account:
    """One shell line as the account, in a LOGIN shell (its profile: what
    its installers put on PATH), exactly as the worker's as_login runs it.
    The PATH is re-asserted INSIDE the shell: Debian's /etc/profile assigns
    PATH outright for a non-root login, so what env -i set would be gone
    by the time the line runs (found by the Debian smoke container, which
    then downloaded the real claude in place of the test's fake)."""

    def __init__(self, login: str, home: str, sudo: str):
        self.login, self.home, self.sudo = login, home, sudo.split()

    def run(self, line: str, *, stderr=None) -> bytes:
        p = f"/usr/local/bin:/usr/bin:/bin:{self.home}/.local/bin"
        cmd = [*self.sudo, "-n", "-u", self.login, "-H", "env", "-i", f"HOME={self.home}", f"PATH={p}",
               f"AGENT_FABRIC_PATH={p}", "bash", "-lc", 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "$HOME" && eval "$1"',
               "_", line]
        return quiet_run(cmd, stderr=stderr)


def quiet_run(cmd: list[str], *, stderr=None) -> bytes:
    sys.stderr.flush()
    try:
        return run_bounded(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr,
                           timeout=READBACK_TIMEOUT_S).stdout
    except subprocess.TimeoutExpired:
        print(f"new-agent:    {cmd[0]}: no answer within {READBACK_TIMEOUT_S} s", file=sys.stderr)
        return b""
    except OSError as exc:
        # A command that cannot start is bash's own error line, written where
        # the command's stderr went: into the pipe when it was merged there
        # (the ping's `2>&1 | tail -n +2` drops it), on stderr otherwise.
        msg = f"{cmd[0]}: {exc.strerror or exc}\n"
        if stderr is subprocess.STDOUT:
            return msg.encode("utf-8", "surrogateescape")
        print(f"new-agent:    {msg}", end="", file=sys.stderr)
        return b""


def prefixed(prefix: str, out: bytes, *, skip: int = 0) -> None:
    """`… | sed 's/^/<prefix>/' >&2`: every line, the last one completed."""
    for line in out.splitlines()[skip:]:
        sys.stderr.buffer.write(prefix.encode() + line + b"\n")
    sys.stderr.buffer.flush()


def verify(root: str, login: str, home: str, sudo: str, projects: list[str], *, account: str = "",
           no_account: bool = False) -> tuple[str, str]:
    """Step 10: what the account can do now, read back as it, then the
    list of what only a person can do; and, when the run named a Claude
    account (`<slug>=<fp12>`), the failure line if its token is not the one
    applied ("" when it is, or when none was named). Nothing here changes
    the account."""
    a = Account(login, home, sudo)
    first = projects[0] if projects else ""
    where = f"~/projects{'/' + first if first else ''}"
    prefixed("   ", a.run("~/projects/agent-fabric/bin/fabric-secrets status 2>&1 | grep -E 'missing|OK|NOT OK'"))
    prefixed("   gh: ", a.run("gh auth status 2>&1 | grep -o 'Logged in.*' | head -1"))
    for pid in projects:
        prefixed(f"   {pid} ", a.run(f"timeout 20 git -C ~/projects/'{pid}' ls-remote --heads origin >/dev/null 2>&1 "
                                      "&& echo 'ssh to origin: ok' || echo 'ssh to origin: FAILED'"))
    prefixed("   ", a.run("printf 'git: %s <%s> signingkey=%s gpgsign=%s\\n' \"$(git config --global user.name)\" "
                          "\"$(git config --global user.email)\" \"$(git config --global user.signingkey | cut -c1-12)\" "
                          "\"$(git config --global commit.gpgsign)\""))
    # The secret of the key git signs with, not any secret key: since
    # ADR-038 every account holds its own store key, so a count of secret
    # keys was never zero and the hand-off below was never asked for
    # (rust-ui-dev-01 could not commit, 2026-10-03, seq 11160).
    # The listing only when gpg answered 0, as fabric-ctl keys reads it
    # (ops.mjs signingSecret): gpg can list a key and still exit non-zero
    # (a keyring it could not fully read), and that is no clean answer.
    listing = a.run('k="$(git config --global user.signingkey)"; [ -n "$k" ] && '
                    'out="$(gpg --list-secret-keys --with-colons -- "$k")" && printf "%s\\n" "$out"',
                    stderr=subprocess.DEVNULL).decode("utf-8", "replace")
    signing = "present" if signs_with_secret(listing) else "absent"
    for prov in ("anthropic", "openrouter"):
        prefixed(f"   launch ({prov}): ", a.run(f"cd {where} && ~/projects/agent-fabric/runtime/openrouter/launch "
                                                  f"--provider {prov} --print 2>&1 | grep -E '^launch:|resolved profile' | head -1"))
    # The control agent bootstrap enabled in the account's user manager
    # answers the coordinator from here on: one ping, as the operator.
    prefixed("   control plane: ", quiet_run([f"{root}/bin/fabric-ctl", login, "ping"], stderr=subprocess.STDOUT), skip=1)
    applied = applied_token(home, sudo)
    if account:
        slug, want = account.split("=", 1)
        if applied == want:
            return closing(login, signing, "applied", first, account=account), ""
        got = "no token" if applied is None else f"token {applied}"
        return (closing(login, signing, "not-applied", first, account=account),
                f"new-agent: step failed: Claude account {slug}: CLAUDE_CODE_OAUTH_TOKEN not applied (expected {want}, "
                f"{got} in {home}/.config/agent-fabric/secrets.env) — fabric-secrets sync as {login}, then re-run\n")
    if no_account:
        return closing(login, signing, "declined", first), ""
    return closing(login, signing, "template" if applied is not None else "no", first), ""


def applied_token(home: str, sudo: str) -> str | None:
    """The fingerprint (sha256[:12]) of the CLAUDE_CODE_OAUTH_TOKEN the
    account's sync applied, read as root, or None when there is none. The
    value stays in this process and only its fingerprint leaves it, the
    one fabric-secrets store templates prints. A line sync did not write
    (two exports, or one that is not one shell word) is no answer, and
    compares as no token."""
    r = run_bounded([*sudo.split(), "-n", "sed", "-n", "s/^export CLAUDE_CODE_OAUTH_TOKEN=//p",
                     f"{home}/.config/agent-fabric/secrets.env"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=READBACK_TIMEOUT_S)
    lines = r.stdout.decode("utf-8", "surrogateescape").splitlines()
    if r.returncode != 0 or len(lines) != 1:
        return None
    try:
        words = shlex.split(lines[0])
    except ValueError:
        return None
    if len(words) != 1 or not words[0]:
        return None
    return hashlib.sha256(words[0].encode("utf-8", "surrogateescape")).hexdigest()[:12]


def signs_with_secret(listing: str) -> bool:
    """Whether a `gpg --list-secret-keys --with-colons` listing holds a key
    or subkey that can sign and whose secret is really here. gpg lists a
    stub (field 15 `#`: the secret is elsewhere, or was exported away) and
    exits 0 for it, so the exit status said present where commits could
    not sign. The rule is runtime/control/ops.mjs signingSecret's, so
    fabric-ctl keys and this read-back agree."""
    for line in listing.splitlines():
        f = line.split(":")
        capabilities = f[11] if len(f) > 11 else ""
        token = f[14] if len(f) > 14 else None
        if f[0] in ("sec", "ssb") and "s" in capabilities and token != "#":
            return True
    return False


def closing(login: str, signing: str, creds: str, first: str, *, account: str = "") -> str:
    """What is left for a person, in a terminal. A Claude account for plain
    claude is a template's token, assigned into the login's store and synced
    into its secrets.env (docs/adr/ADR-031-claude-accounts-assigned-applied-
    and-proved-by-signed-action.md) — the launcher starts no plain-claude
    session without one. Never a copy of another login's .credentials.json:
    a refresh token has one holder, and the first renewal by either signs
    the other out."""
    if signing == "present":
        gpg = "- GPG secret key: the signing key's, present"
    else:
        gpg = ("- GPG secret key: the signing key's is NOT in this account's keyring — commits will fail to "
               "sign. As the coordinator, in a terminal (the key has a passphrase):\n"
               f'       gpg --export-secret-keys "$(git config --get user.signingkey)" | sudo -u {login} gpg --batch --import\n'
               f"       sudo -u {login} bash -c \"echo '$(git config --get user.signingkey):6:' | gpg --import-ownertrust\"")
    slug, _, fp = account.partition("=")
    if creds == "applied":
        claude = f"- Claude account: {slug} (token {fp}), applied (plain-claude path ready)"
    elif creds == "not-applied":
        claude = (f"- Claude account: {slug} (token {fp}) was assigned and is NOT applied — the launcher refuses a "
                  f"plain-claude session until it is. As {login}: projects/agent-fabric/bin/fabric-secrets sync")
    elif creds == "template":
        claude = "- Claude account: a template token (plain-claude path ready)"
    else:
        lead = "not assigned (--no-claude-account: the broker path only); " if creds == "declined" else ""
        claude = (f"- Claude account: {lead}no template token — the launcher refuses a plain-claude session (--provider "
                  "anthropic) without one, its own /login included; the broker path does not need one.\n"
                  f"       As the coordinator: bin/fabric-accounts assign {login} <account> (docs/adr/ADR-031-claude-"
                  "accounts-assigned-applied-and-proved-by-signed-action.md). Never copy another login's "
                  ".credentials.json.")
    # "done" only when nothing failed: a Claude account not applied is a
    # failed step, said on the line after this list.
    head = "new-agent: NOT done — the Claude account is not applied (below)." if creds == "not-applied" \
        else "new-agent: done."
    return (f"{head} Left for a person, in a terminal (nothing here can do them):\n"
            f"   {gpg}\n"
            f"   {claude}\n"
            "   - first launch (bootstrap has trusted its folders in Claude Code; no trust question):\n"
            f"       moveto {login}{' ' + first if first else ''}   then   runtime/openrouter/launch\n")


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if cmd == "args":
            sys.stdout.write(args(rest))
        elif cmd == "host-check" and len(rest) == 1:
            sys.stdout.write(host_check(rest[0]))
        elif cmd == "audit" and len(rest) >= 4:
            sys.stderr.write(audit(rest[0], rest[1], rest[2], rest[3], rest[4:]))
        elif cmd == "claude-want" and len(rest) in (1, 2):
            print(claude_want(rest[0], rest[1] if len(rest) == 2 else ""))
        elif cmd == "subids" and len(rest) == 2:
            sys.stdout.write(subids(*rest))
        elif cmd == "missing-keys" and len(rest) == 1:
            sys.stdout.write(missing_keys(rest[0], sys.stdin.read()))
        elif cmd == "verify" and len(rest) >= 4:
            opts, projects = rest[4:], []
            account, no_account = "", False
            for a in opts:
                if a.startswith("--claude-account=") and CLAUDE_ACCOUNT.fullmatch(a[len("--claude-account="):]):
                    account = a[len("--claude-account="):]
                elif a == "--no-claude-account":
                    no_account = True
                elif a.startswith("-"):
                    print(f"new_agent_worker.py: verify: unknown argument {a}", file=sys.stderr)
                    return 2
                else:
                    projects.append(a)
            text, failed = verify(rest[0], rest[1], rest[2], rest[3], projects, account=account, no_account=no_account)
            sys.stderr.write(text + failed)
            if failed:
                return 1
        else:
            print(f"new_agent_worker.py: no such call: {' '.join(argv)}", file=sys.stderr)
            return 2
    except Exit as exc:
        print(exc.msg, file=sys.stderr)
        return exc.code
    # A question that got no answer is not a "no": host-check's account is
    # neither present nor absent, and verify does not guess at a token.
    except subprocess.TimeoutExpired as exc:
        print(f"new-agent: {exc.cmd[0]}: no answer within {exc.timeout:g} s", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"new-agent: {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
