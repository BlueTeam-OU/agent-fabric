#!/usr/bin/env python3
"""tools/fabric/provisioning/persist_accounts.py — make the named accounts
survive this host's reboot, the way this platform needs. Root, via sudo, on
the host the accounts live on; idempotent; run by the new-agent worker
after useradd and by `bin/fabric-host <host> persist` for every placement
(the one-time migration of accounts made before this existed, 2026-09-17).
Ported from runtime/provisioning/persist-accounts.sh (agent-fabric ADR-040,
off shell).

    persist_accounts.py <login>...

Every platform: `loginctl enable-linger <login>`, so the account's user
manager — and the control agent under it — runs without a login. On a Qubes
AppVM (host_platform: persists_across_reboot is False) the account records
themselves are volatile too: each login's line from /etc/{passwd,shadow,
group,gshadow,subuid,subgid} is written into the snapshot
/rw/config/agent-fabric/accounts/ (root, 0600), replacing an older line for
the same name — each file swapped into place whole, so a crash mid-write
leaves the previous snapshot, never a partial one — plus the login's
supplementary groups (`members`: login:g1,g2, from the live /etc/group, so
the shared-cache membership the worker grants comes back too), and the boot
script platform/qubes/agent-fabric-accounts.rc is installed under
/rw/config/rc.local.d/ and refreshed whenever this checkout's copy differs.
Nothing on a persistent platform writes a snapshot. Secrets: the shadow line
carries a hash, never a password; the snapshot directory is root's alone.

Also on every platform: the host-wide lease directory the accounts share,
/run/lock/agent-fabric (bin/fabric-lease, ADR-010) — made now, 1777, and
made to come back after a reboot: by the boot script above on a Qubes
AppVM, by a tmpfiles.d entry (platform/agent-fabric.tmpfiles.conf ->
/etc/tmpfiles.d/) where /etc persists.

CONTRACT, frozen from the shell
  argv    one or more logins; none is a usage line on stderr, exit 2
  env     AGENT_FABRIC_ACCOUNTS_SNAPSHOT (/rw/config/agent-fabric/accounts),
          AGENT_FABRIC_RC_LOCAL_D (/rw/config/rc.local.d), AGENT_FABRIC_ETC
          (/etc), AGENT_FABRIC_LEASES (/run/lock/agent-fabric),
          AGENT_FABRIC_TMPFILES_D (/etc/tmpfiles.d), AGENT_FABRIC_LOGINCTL
          (loginctl), AGENT_FABRIC_LOCK_WAIT (30 s), AGENT_FABRIC_PLATFORM
  stderr  every refusal, as `persist-accounts: <why>`
  exit    0 done; 1 any step failed (the rest still ran, a login at a time)
          or the snapshot is locked by another writer or cannot be made;
          2 usage
  kept    the boot script's install is not checked (its failure is not
          counted): the shell did not, and a change there is a finding for
          the rule's owner, not a port's choice
"""
from __future__ import annotations

import filecmp
import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from provisioning import host_platform  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LOGINCTL_TIMEOUT_S = 60
RECORD_FILES = ("passwd", "shadow", "group", "gshadow", "subuid", "subgid")


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def _install_dir(path: str, mode: int) -> None:
    """install -d -m MODE PATH: made with parents, and the mode set whatever the umask."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, mode)


def _install_file(src: str, dst: str, mode: int) -> None:
    """install -m MODE SRC DST: the file replaced whole, never half-written."""
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=os.path.dirname(dst))
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as fh:
            shutil.copyfileobj(fh, out)
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _same(a: str, b: str) -> bool:
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _lines(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def _put_line(snap: str, name: str, login: str, line: str) -> None:
    """Replace-or-append the login's line in one snapshot file, atomically."""
    kept = [ln for ln in _lines(os.path.join(snap, name)) if not ln.startswith(login + ":")]
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=snap)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write("".join(f"{ln}\n" for ln in [*kept, line]))
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(snap, name))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _account_exists(login: str, etc: str) -> bool:
    """`getent passwd` as a command (a test fakes it on PATH, and a directory service answers it), else the records."""
    try:
        if subprocess.run(["getent", "passwd", login], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=LOGINCTL_TIMEOUT_S).returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return any(ln.startswith(login + ":") for ln in _lines(os.path.join(etc, "passwd")))


def _supplementary_groups(login: str, etc: str) -> str:
    names = []
    for ln in _lines(os.path.join(etc, "group")):
        fields = ln.split(":")
        if len(fields) >= 4 and login in fields[3].split(","):
            names.append(fields[0])
    return ",".join(names)


def _lock(snap: str, wait_s: float):
    """The snapshot's writer lock, held for the life of the process; None when another writer holds it."""
    fh = open(os.path.join(snap, ".lock"), "w")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            if time.monotonic() >= deadline:
                fh.close()
                return None
            time.sleep(0.05)


def run(logins: list[str], environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    snap = env.get("AGENT_FABRIC_ACCOUNTS_SNAPSHOT") or "/rw/config/agent-fabric/accounts"
    rcd = env.get("AGENT_FABRIC_RC_LOCAL_D") or "/rw/config/rc.local.d"
    etc = env.get("AGENT_FABRIC_ETC") or "/etc"
    leases = env.get("AGENT_FABRIC_LEASES") or "/run/lock/agent-fabric"
    tmpfiles_d = env.get("AGENT_FABRIC_TMPFILES_D") or "/etc/tmpfiles.d"
    loginctl = env.get("AGENT_FABRIC_LOGINCTL") or "loginctl"
    if not logins:
        _say("usage: persist_accounts.py <login>...")
        return 2
    prof = host_platform.profile(host_platform.detect(env))
    platform_dir = os.path.join(ROOT, "runtime", "provisioning", "platform")
    rc = 0
    try:
        _install_dir(leases, 0o1777)
    except OSError:
        _say(f"persist-accounts: cannot make the lease directory {leases}")
        rc = 1
    if prof.persists_across_reboot:
        src = os.path.join(platform_dir, "agent-fabric.tmpfiles.conf")
        dst = os.path.join(tmpfiles_d, "agent-fabric.conf")
        if not _same(src, dst):
            try:
                _install_dir(tmpfiles_d, 0o755)
                _install_file(src, dst, 0o644)
            except OSError:
                rc = 1
    lock = None
    if not prof.persists_across_reboot:
        try:
            _install_dir(snap, 0o700)
        except OSError:
            return 1
        try:
            wait = float(env.get("AGENT_FABRIC_LOCK_WAIT") or 30)
        except ValueError:
            wait = 30.0
        lock = _lock(snap, wait)       # held until the process ends
        if lock is None:
            _say("persist-accounts: the snapshot is locked by another writer")
            return 1
    for login in logins:
        if not _account_exists(login, etc):
            _say(f"persist-accounts: no such account: {login}")
            rc = 1
            continue
        if not prof.persists_across_reboot:
            try:
                _install_dir(snap, 0o700)
            except OSError:
                rc = 1
                continue
            for name in RECORD_FILES:
                if not os.path.isfile(os.path.join(etc, name)):
                    continue
                line = next((ln for ln in _lines(os.path.join(etc, name)) if ln.startswith(login + ":")), "")
                if line:
                    try:
                        _put_line(snap, name, login, line)
                    except OSError:
                        rc = 1
            try:
                _put_line(snap, "members", login, f"{login}:{_supplementary_groups(login, etc)}")
            except OSError:
                rc = 1
            src = os.path.join(platform_dir, "qubes", "agent-fabric-accounts.rc")
            dst = os.path.join(rcd, "agent-fabric-accounts.rc")
            if not _same(src, dst):
                try:
                    _install_dir(rcd, 0o755)
                    _install_file(src, dst, 0o755)
                except OSError:
                    pass                  # as the shell: not counted (see the header)
        try:
            done = subprocess.run([loginctl, "enable-linger", login], stderr=subprocess.DEVNULL, timeout=LOGINCTL_TIMEOUT_S)
            failed = done.returncode != 0
        except (OSError, subprocess.TimeoutExpired):
            failed = True
        if failed:
            _say(f"persist-accounts: enable-linger failed for {login}")
            rc = 1
    if lock is not None:
        lock.close()
    return rc


def main(argv: list[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
