#!/usr/bin/env python3
"""tools/fabric/provisioning/ssh_add_login.py — let the operator's ssh reach ONE
more account on a host whose sshd ssh-operator.sh has already staged
(agent-fabric ADR-048; j81): the login is added to AllowUsers and given its
root-owned keys file, from that staging, and the staged restore.sh applies
it. No reboot, no new key, no registry read.

    ssh_add_login.py <login>        as root, via sudo, on the host the account is on

Run by the new-agent worker (step 9b) for a login it has just made, on a host
whose registry entry pins an sshd. Idempotent: the same login again changes
nothing and restarts sshd once more.

WHAT IT TRUSTS, and refuses to go on without (each is a refusal, exit 1, one
`ssh-add-login: <why>` line, and nothing written before it):
  the staging  AGENT_FABRIC_SSH_STAGE (/rw/config/agent-fabric-ssh) is a
               directory, and its drop-in, its authorized_keys directory and
               files, and restore.sh are each root-owned, not a symlink and
               not writable by group or others — a file an account could write
               would put the operator's door in its hands, and restore.sh is
               run as root. The drop-in holds exactly one AllowUsers line.
  the key      the operator key is READ from the keys files ssh-operator.sh
               staged — never argv or the environment — and every one must
               carry the same, in exactly the shape ssh-operator.sh writes
               (command="<libexec>/enter-ssh",restrict,pty <type> <base64>). A
               staging that is odd or disagrees with itself is the owner's to
               look at, not to be repaired here.
  the account  a plain lowercase login name (no space, newline or pattern
               character: AllowUsers is the fence's first rung, ADR-048 §4,
               and a name like that would write more than one rule into it),
               not root, with an account on this host whose uid is not a system
               one and whose comment is `agent-fabric <role>` — the one the
               worker's useradd leaves. Another account is not this script's to
               open the operator's ssh to.
Who can run it is who can run anything as root here: the worker reaches it
with `sudo -n` from the coordinator's login, as it reaches useradd; it adds
no authority. The names AllowUsers already holds are checked as names too.

CONTRACT
  env     AGENT_FABRIC_SSH_STAGE, AGENT_FABRIC_SSH_LIBEXEC
          (/usr/local/libexec/agent-fabric): the same two ssh-operator.sh reads
  stderr  every refusal, `ssh-add-login: <why>`; on success one line
  exit    0 done; 1 a refusal or a failed restore.sh; 2 usage
"""
from __future__ import annotations

import fcntl
import os
import pwd
import re
import stat
import subprocess
import sys
from collections.abc import Callable

LOGIN = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
# The key shapes ssh-operator.sh accepts, and nothing else.
KEY = re.compile(r"(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com) AAAA[A-Za-z0-9+/]+=*")
GECOS_PREFIX = "agent-fabric "
UID_MIN = 1000
RESTORE_TIMEOUT_S = 120


class Refused(Exception):
    pass


def trusted(path: str, owner: int, *, directory: bool = False) -> None:
    """Refuse a path an account could have changed: not what it should be, not
    owned by `owner`, or writable by group or others. lstat, so a symlink is
    never followed into a place the staging does not hold."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise Refused(f"{path}: {exc.strerror}") from exc
    if not (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)):
        raise Refused(f"{path} is not a {'directory' if directory else 'regular file'}")
    if st.st_uid != owner or st.st_mode & 0o022:
        raise Refused(f"{path} is not owned by uid {owner} and closed to group and others")


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise Refused(f"{path}: {getattr(exc, 'strerror', None) or 'not UTF-8'}") from exc


def check_account(login: str, entry: pwd.struct_passwd | None, uid_min: int) -> None:
    if not LOGIN.fullmatch(login):
        raise Refused(f"{login!r} is not a plain login name")
    if login == "root":
        raise Refused("root is never reachable over the operator's ssh")
    if entry is None:
        raise Refused(f"{login} has no account on this host")
    if entry.pw_uid < uid_min:
        raise Refused(f"{login} is a system account (uid {entry.pw_uid})")
    if not entry.pw_gecos.startswith(GECOS_PREFIX):
        raise Refused(f"{login} was not made by new-agent (its account comment is not 'agent-fabric <role>')")


def operator_key(stage: str, libexec: str, owner: int) -> str:
    keys = os.path.join(stage, "authorized_keys")
    trusted(keys, owner, directory=True)
    # Dotfiles are skipped as restore.sh's glob skips them: a temporary file a killed run left must not block every later one.
    names = sorted(n for n in os.listdir(keys) if not n.startswith("."))
    if not names:
        raise Refused(f"no keys file is staged in {keys}; run ssh-operator.sh first")
    prefix = f'command="{libexec}/enter-ssh",restrict,pty '
    found: str | None = None
    for name in names:
        path = os.path.join(keys, name)
        trusted(path, owner)
        text = read_text(path)
        key = text[len(prefix):-1] if text.startswith(prefix) and text.endswith("\n") else ""
        if not KEY.fullmatch(key):
            raise Refused(f"{path} is not the one forced-command line ssh-operator.sh writes")
        if found is not None and found != key:
            raise Refused("the staged keys files carry different operator keys")
        found = key
    assert found is not None
    return found


def allow_users(conf_text: str, path: str) -> tuple[list[str], list[str]]:
    """(the drop-in's lines, the names AllowUsers holds), after exactly one such line."""
    lines = conf_text.split("\n")
    at = [i for i, ln in enumerate(lines) if ln.startswith("AllowUsers ")]
    if len(at) != 1:
        raise Refused(f"{path} does not hold exactly one AllowUsers line")
    names = lines[at[0]].split()[1:]
    for n in names:
        if not LOGIN.fullmatch(n):
            raise Refused(f"{path} names {n!r}, which is not a plain login")
    return lines, names


def replace(path: str, text: str, mode: int, owner: int) -> None:
    """Beside the target and renamed whole: the boot-time restore never reads half of one."""
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{os.getpid()}.new")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if os.geteuid() == 0:
            os.chown(tmp, owner, -1)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_restore(path: str) -> None:
    try:
        done = subprocess.run([path], stdin=subprocess.DEVNULL, timeout=RESTORE_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise Refused(f"{path} did not finish within {RESTORE_TIMEOUT_S} s; the login is staged, sshd may not have restarted") from None
    except OSError as exc:
        raise Refused(f"{path}: {exc.strerror}") from exc
    if done.returncode != 0:
        raise Refused(f"{path} exited {done.returncode}; the login is staged, sshd may not have restarted")


def add_login(login: str, stage: str, libexec: str, *, entry: pwd.struct_passwd | None, owner: int = 0,
              uid_min: int = UID_MIN, restore: Callable[[str], None] = run_restore) -> None:
    check_account(login, entry, uid_min)
    trusted(stage, owner, directory=True)
    with locked(stage):
        _add_locked(login, stage, libexec, owner, restore)


def locked(stage: str):
    """One run at a time per staging, from the read of the drop-in to the end of restore.sh: two logins provisioned
    together would each read AllowUsers before the other wrote it, and the later write would drop the earlier name
    while its worker reported success. The lock file is the staging's own (root-owned); a stale one is no lock,
    since flock dies with its holder."""
    class Lock:
        def __enter__(self):
            self.fd = os.open(os.path.join(stage, ".ssh-add-login.lock"), os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX)

        def __exit__(self, *exc):
            os.close(self.fd)
    return Lock()


def _add_locked(login: str, stage: str, libexec: str, owner: int, restore: Callable[[str], None]) -> None:
    conf = os.path.join(stage, "50-agent-fabric.conf")
    trusted(conf, owner)
    restore_sh = os.path.join(stage, "restore.sh")
    trusted(restore_sh, owner)
    lines, names = allow_users(read_text(conf), conf)
    key = operator_key(stage, libexec, owner)
    # Everything is judged before the first write.
    names = sorted({*names, login})
    lines = [f"AllowUsers {' '.join(names)}" if ln.startswith("AllowUsers ") else ln for ln in lines]
    # The keys file first: a crash between the two leaves a login with a key and no AllowUsers entry, which sshd refuses.
    replace(os.path.join(stage, "authorized_keys", login), f'command="{libexec}/enter-ssh",restrict,pty {key}\n', 0o644, owner)
    replace(conf, "\n".join(lines), 0o600, owner)
    restore(restore_sh)


def main(argv: list[str], environ: dict[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    if len(argv) != 1:
        print("usage: ssh_add_login.py <login>", file=sys.stderr)
        return 2
    login = argv[0]
    try:
        try:
            entry = pwd.getpwnam(login)
        except KeyError:
            entry = None
        add_login(login, env.get("AGENT_FABRIC_SSH_STAGE") or "/rw/config/agent-fabric-ssh",
                  env.get("AGENT_FABRIC_SSH_LIBEXEC") or "/usr/local/libexec/agent-fabric", entry=entry)
    except Refused as exc:
        print(f"ssh-add-login: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ssh-add-login: {exc.filename or ''}: {exc.strerror}", file=sys.stderr)
        return 1
    print(f"ssh-add-login: {login} is reachable over the operator's ssh", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
