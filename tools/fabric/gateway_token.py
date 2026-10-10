#!/usr/bin/env python3
"""tools/fabric/gateway_token.py — the login's Claude credential as a token file the gateway reads
(the fleet gateway's control-plane contract §10, "Token file checks"; gateway-switch s5).

`fabric-secrets sync` (secrets_sync.py) calls write() with the login's CLAUDE_CODE_OAUTH_TOKEN, the setup-token it
already exports to secrets.env; the plan (gateway_plan.py) names token_path() as the `claude-subscription` profile's
file. Replacing the file is how `fabric-accounts assign` takes effect on the gateway's next request, with no new plan
generation and no session restart.

CONTRACT
  token_path(uid)   <runtime root>/<uid>/agent-fabric/gateway/claude-subscription.token, the runtime root being
                    /run/user: a tmpfs only the login can enter. Absolute and in normal form, as the gateway requires.
  write(token, uid) the file holds the token's bytes, no newline; mode 0600, owned by the login; written by a new
                    file in the same directory (mkstemp: O_EXCL, 0600) and renamed over the old one, so a change is a
                    new inode, a new generation, and a reader never sees half a token. The same token again is
                    "unchanged": the file is left, its inode too. Returns "written", "unchanged".
  remove(uid)       the file is taken away when the store no longer holds a token: "removed" or "absent". A gateway
                    then fails that attempt closed (credential_unavailable) rather than serving an account the
                    login was taken off.
  A path the gateway would refuse is refused here first, naming the first check that failed: a component that is a
  symlink; a directory not owned by the login or root, or writable by group or other; any directory carrying a
  default ACL, or an ACL entry for another user or group that grants write (on Linux the mask is the group bits, so
  the mode check refuses it first; the ACL check stays as the second line); a filesystem the permission checks
  cannot read whole (only ext2/3/4, xfs, btrfs and tmpfs are admitted). A file that carries an ACL entry is not
  refused but replaced by a new 0600 file with none. The runtime directory
  /run/user/<uid> must exist: it is the login's own, made by the session manager, and is not made here.
  The checks run from `check_from` (default /, as the gateway does) down; a test names the directory it made.
  Errors are TokenFileError with one line, never carrying the token: every failure of the filesystem (no space, a
  directory the login cannot write, an unreadable mount table) is one too, so a caller has one thing to catch.
  Nothing is logged: the token is not in any message, argument, environment or exception."""
from __future__ import annotations

import contextlib
import os
import re
import stat
import struct
import sys
import tempfile
from collections.abc import Callable

RUNTIME_ROOT = "/run/user"
SUBDIRS = ("agent-fabric", "gateway")
NAME = "claude-subscription.token"
# The filesystems whose permissions the gateway's checks read whole (contract §10).
ADMITTED_FS = frozenset({"ext2", "ext3", "ext4", "xfs", "btrfs", "tmpfs"})
ACL_ACCESS, ACL_DEFAULT = "system.posix_acl_access", "system.posix_acl_default"
_ACL_USER, _ACL_GROUP, _ACL_MASK = 0x02, 0x08, 0x10


class TokenFileError(Exception):
    """The token file cannot be written the way the gateway will read it: one line, naming the first check that failed."""


def token_path(uid: int, runtime_root: str = RUNTIME_ROOT) -> str:
    return os.path.join(runtime_root, str(uid), *SUBDIRS, NAME)


def filesystem_of(path: str, mountinfo: str = "/proc/self/mountinfo") -> str:
    """The type of the filesystem path lies on: the longest mount point of /proc/self/mountinfo that contains it."""
    real, best, kind = os.path.realpath(path), "", ""
    with open(mountinfo, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            left, _, right = line.partition(" - ")
            fields = left.split()
            if len(fields) < 5 or not right:
                continue
            mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
            # >= : of several mounts on one mount point the last listed is the visible one.
            if (real == mount or real.startswith(mount.rstrip("/") + "/")) and len(mount) >= len(best):
                best, kind = mount, right.split()[0]
    return kind


def _acl(path: str, name: str) -> bytes | None:
    try:
        return os.getxattr(path, name, follow_symlinks=False)
    except OSError as e:
        if e.errno in (getattr(os, "ENODATA", 61), 95):      # no ACL there, or the filesystem has none
            return None
        raise TokenFileError(f"{path}: the ACL cannot be read ({e.strerror or e.errno})") from None


def _extended_entries(acl: bytes) -> list[tuple[int, int]]:
    """(tag, permissions after the mask) of every named-user and named-group entry of a posix_acl xattr."""
    entries = [struct.unpack_from("<HHI", acl, off)[:2] for off in range(4, len(acl) - 7, 8)]
    mask = next((p for tag, p in entries if tag == _ACL_MASK), 7)
    return [(tag, perm & mask) for tag, perm in entries if tag in (_ACL_USER, _ACL_GROUP)]


def check_directory(path: str, uid: int) -> None:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise TokenFileError(f"{path}: not a plain directory (a symlink or something else); the gateway refuses a link anywhere on the path")
    if st.st_uid not in (uid, 0):
        raise TokenFileError(f"{path}: owned by uid {st.st_uid}, neither the login nor root")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise TokenFileError(f"{path}: writable by group or other")
    if _acl(path, ACL_DEFAULT) is not None:
        raise TokenFileError(f"{path}: carries a default ACL; the replacement file would inherit it")
    acl = _acl(path, ACL_ACCESS)
    if acl is not None and any(perm & 2 for _tag, perm in _extended_entries(acl)):
        raise TokenFileError(f"{path}: an ACL entry for another user or group grants write")


def _check_path(path: str, uid: int, fs_of: Callable[[str], str], check_from: str) -> None:
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise TokenFileError(f"{path}: not an absolute path in normal form")
    below = os.path.relpath(os.path.dirname(path), check_from)
    here = check_from
    check_directory(here, uid)
    for part in [] if below == "." else below.split(os.sep):
        here = os.path.join(here, part)
        check_directory(here, uid)
    kind = fs_of(os.path.dirname(path))
    if kind not in ADMITTED_FS:
        raise TokenFileError(f"{os.path.dirname(path)}: on a {kind or 'unknown'} filesystem; the gateway's permission checks read only "
                             "ext2/3/4, xfs, btrfs and tmpfs whole")


def _make_dirs(path: str, uid: int, runtime_root: str) -> None:
    """The login's runtime directory must exist; the two below it are made 0700 when they are not there."""
    top = os.path.join(runtime_root, str(uid))
    if not os.path.isdir(top):
        raise TokenFileError(f"{top}: the login's runtime directory does not exist (no session manager has made it)")
    here = top
    for part in SUBDIRS:
        here = os.path.join(here, part)
        try:
            os.mkdir(here, 0o700)
        except FileExistsError:
            pass
        except OSError as e:
            raise TokenFileError(f"{here}: cannot be made ({e.strerror or e.errno})") from None


def _read(path: str) -> bytes | None:
    """The file as the gateway opens it: no symlink followed. None when it is not there."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise TokenFileError(f"{path}: cannot be opened ({e.strerror or e.errno}); a link in its place is refused") from None
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise TokenFileError(f"{path}: not a regular file")
        return fh.read(1 << 16)


def write(token: str, uid: int | None = None, runtime_root: str = RUNTIME_ROOT,
          fs_of: Callable[[str], str] = filesystem_of, check_from: str = os.sep) -> str:
    uid = os.getuid() if uid is None else uid
    # A setup-token is printable ASCII; it goes into an Authorization header, where nothing else is a valid value.
    if not token or any(not 0x21 <= ord(c) <= 0x7E for c in token):
        raise TokenFileError("the token is empty or carries a space, a control character or a non-ASCII one; nothing written")
    path = token_path(uid, runtime_root)
    try:
        _make_dirs(path, uid, runtime_root)
        _check_path(path, uid, fs_of, check_from)
        data = token.encode("utf-8")
        current = _read(path)
        if current is not None and current == data:
            st = os.lstat(path)
            if stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == uid and _acl(path, ACL_ACCESS) is None:
                return "unchanged"
        directory = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{NAME}.")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fchmod(fh.fileno(), 0o600)
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
        return "written"
    except OSError as e:
        raise TokenFileError(f"{path}: cannot be written ({e.strerror or e.errno})") from None


def remove(uid: int | None = None, runtime_root: str = RUNTIME_ROOT) -> str:
    path = token_path(os.getuid() if uid is None else uid, runtime_root)
    try:
        os.unlink(path)
    except FileNotFoundError:
        return "absent"
    except OSError as e:
        raise TokenFileError(f"{path}: cannot be removed ({e.strerror or e.errno})") from None
    return "removed"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["path"] or (len(args) == 2 and args[0] == "path"):
        print(token_path(int(args[1]) if len(args) == 2 else os.getuid()))
        return 0
    print("usage: gateway_token.py path [uid]    (the file is written by `fabric-secrets sync`)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
