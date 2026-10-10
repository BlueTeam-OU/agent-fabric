#!/usr/bin/env python3
"""tools/fabric/gateway_token.py: the login's Claude credential as the token file the gateway reads (control-plane
contract §10): its path, mode and owner, a change as a new file renamed over the old, the checks the gateway makes
made first, and the token in no error. A scratch directory stands for /run/user, its filesystem told as tmpfs.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gateway_token as g  # noqa: E402

TOKEN = "sk-ant-oat01-" + "a" * 60
UID = os.getuid()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    tmpfs = lambda _p: "tmpfs"  # noqa: E731
    # Directories a case makes in more than one step get the mode the test names, whatever umask the runner has:
    # makedirs applies its mode to the leaf alone, and a login with umask 0002 (the Debian CI user) made the middle
    # one group-writable, which the gateway's check rightly refuses.
    os.umask(0o022)

    def fresh(base: str, name: str) -> str:
        root = os.path.join(base, name)
        os.makedirs(os.path.join(root, str(UID)), mode=0o700)
        os.chmod(root, 0o755)
        return root

    def write(root: str, token: str = TOKEN, fs=tmpfs) -> str:
        return g.write(token, UID, root, fs, root)

    def refusal(root: str, token: str = TOKEN, fs=tmpfs) -> str:
        try:
            write(root, token, fs)
            return ""
        except g.TokenFileError as e:
            return str(e)

    with tempfile.TemporaryDirectory() as base:
        print("the path")
        check("/run/user/<uid>/agent-fabric/gateway/claude-subscription.token, absolute and in normal form",
              g.token_path(1000) == "/run/user/1000/agent-fabric/gateway/claude-subscription.token"
              and os.path.normpath(g.token_path(1000)) == g.token_path(1000))
        out = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "gateway_token.py"), "path", "1000"],
                             capture_output=True, text=True, timeout=30)
        check("the command prints it (the plan names the same path)", out.stdout == g.token_path(1000) + "\n", out.stdout + out.stderr)

        print("a runner whose umask leaves group write")
        old = os.umask(0o002)
        try:
            root = fresh(base, "umask")
            check("the directories the writer makes are 0700 whatever the umask, and the write is accepted", write(root) == "written"
                  and all(stat.S_IMODE(os.stat(os.path.join(root, str(UID), *g.SUBDIRS[:n])).st_mode) == 0o700 for n in (1, 2)))
        finally:
            os.umask(old)

        print("write")
        root = fresh(base, "a")
        path = g.token_path(UID, root)
        check("a first write", write(root) == "written")
        st = os.stat(path)
        check("the file holds the token's bytes, no newline, 0600, owned by the login",
              open(path, "rb").read() == TOKEN.encode() and stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == UID)
        check("…and the two directories made for it are 0700",
              all(stat.S_IMODE(os.stat(os.path.join(root, str(UID), *g.SUBDIRS[:n])).st_mode) == 0o700 for n in (1, 2)))
        ino = st.st_ino
        check("the same token again is unchanged: the inode stays", write(root) == "unchanged" and os.stat(path).st_ino == ino)
        check("a new token is a new inode holding it, and nothing else is left in the directory",
              write(root, TOKEN[:-1] + "b") == "written" and os.stat(path).st_ino != ino and open(path).read().endswith("b")
              and os.listdir(os.path.dirname(path)) == [g.NAME])
        os.chmod(path, 0o644)
        ino = os.stat(path).st_ino
        check("the same token in a file whose mode drifted is written again, 0600",
              write(root) == "written" and stat.S_IMODE(os.stat(path).st_mode) == 0o600 and os.stat(path).st_ino != ino)
        real_replace = os.replace
        def broken(*a, **k):
            raise OSError(28, "No space left on device")
        os.replace = broken
        try:
            try:
                write(root, TOKEN[:-1] + "c")
                kept = False
            except g.TokenFileError as e:
                kept = "cannot be written" in str(e) and "No space" in str(e)
        finally:
            os.replace = real_replace
        check("a rename that fails leaves the old token whole and no temporary file",
              kept and open(path).read() == TOKEN and os.listdir(os.path.dirname(path)) == [g.NAME], str(os.listdir(os.path.dirname(path))))

        print("the checks the gateway makes, made first")
        root = fresh(base, "b")
        write(root)
        gw = os.path.join(root, str(UID), "agent-fabric", "gateway")
        os.chmod(gw, 0o770)
        check("a directory writable by group is refused", "writable by group or other" in refusal(root), refusal(root))
        os.chmod(gw, 0o700)
        os.chmod(os.path.join(root, str(UID)), 0o702)
        check("…or by other, higher up", "writable by group or other" in refusal(root))
        os.chmod(os.path.join(root, str(UID)), 0o700)
        check("a clean tree writes again", write(root) in ("written", "unchanged"))
        elsewhere = os.path.join(base, "elsewhere")
        os.makedirs(elsewhere, mode=0o700)
        root = fresh(base, "c")
        os.makedirs(os.path.join(root, str(UID), "agent-fabric"), mode=0o700)
        os.symlink(elsewhere, os.path.join(root, str(UID), "agent-fabric", "gateway"))
        check("a symlink as a component is refused, and nothing is written through it",
              "not a plain directory" in refusal(root) and os.listdir(elsewhere) == [])
        root = fresh(base, "d")
        os.makedirs(os.path.join(root, str(UID), "agent-fabric", "gateway"), mode=0o700)
        os.symlink(elsewhere, g.token_path(UID, root))
        check("a symlink in the token file's place is refused by name, not followed", "cannot be opened" in refusal(root) or "not a regular" in refusal(root),
              refusal(root))
        root = fresh(base, "e")
        os.makedirs(os.path.join(root, str(UID + 1)), mode=0o700)
        try:
            g.write(TOKEN, UID + 1, root, tmpfs, root)
            other = ""
        except g.TokenFileError as e:
            other = str(e)
        check("a directory owned by someone else (the login is another uid) is refused", "neither the login nor root" in other, other)
        root = fresh(base, "f")
        check("a filesystem the permission checks cannot read whole is refused, named", "overlay filesystem" in refusal(root, fs=lambda _p: "overlay"), refusal(root, fs=lambda _p: "overlay"))
        check("…an unknown one too", "unknown filesystem" in refusal(fresh(base, "f2"), fs=lambda _p: ""))
        check("every admitted type writes", all(write(fresh(base, f"fs-{t}"), fs=lambda _p, t=t: t) == "written" for t in sorted(g.ADMITTED_FS)))
        if shutil.which("setfacl"):
            root = fresh(base, "g")
            write(root)
            gw = os.path.join(root, str(UID), "agent-fabric", "gateway")
            acl = subprocess.run(["setfacl", "-d", "-m", "u::rwx", gw], capture_output=True, timeout=30)
            if acl.returncode == 0:
                check("a directory with a default ACL is refused (the renamed file would inherit it)", "default ACL" in refusal(root), refusal(root))
            subprocess.run(["setfacl", "-k", gw], capture_output=True, timeout=30)
            named = subprocess.run(["setfacl", "-m", "u:nobody:r-x,m::r-x", gw], capture_output=True, timeout=30)
            if named.returncode == 0:
                check("an ACL entry for another user that grants no write is accepted (the positive control)", write(root) in ("written", "unchanged"), refusal(root))
                subprocess.run(["setfacl", "-m", "u:nobody:rwx,m::rwx", gw], capture_output=True, timeout=30)
                check("one that grants write is refused", refusal(root) != "", "accepted")
                subprocess.run(["setfacl", "-b", gw], capture_output=True, timeout=30)
        else:
            print("  (setfacl is not here: the two ACL cases are not run)")
        check("the runtime directory must exist: it is not made here",
              "does not exist" in refusal(os.path.join(base, "nowhere")))
        root = fresh(base, "h")
        for bad in ("", " tok", "tok\n", "to\nk", "to\x00k", "tok ", "a\tb", "a b", "a\x01b", "a\x7fb", "tökén"):
            check(f"a token that is empty or carries whitespace or a control character ({bad!r}) is refused and nothing is written",
                  refusal(root, bad) != "" and not os.path.exists(g.token_path(UID, root)))
        errors = [refusal(fresh(base, f"x{n}"), TOKEN, fs=lambda _p: "nfs") for n in range(2)]
        check("no error carries the token", all(TOKEN not in e and "sk-ant" not in e for e in errors))

        root = fresh(base, "ro")
        write(root)
        gw = os.path.join(root, str(UID), "agent-fabric", "gateway")
        os.chmod(gw, 0o500)
        try:
            failure = refusal(root, TOKEN[:-1] + "z")
        finally:
            os.chmod(gw, 0o700)
        check("a directory the login cannot write into is a TokenFileError, not a bare OSError, and the old token stays",
              "cannot be written" in failure and TOKEN[:-1] + "z" not in failure and open(g.token_path(UID, root)).read() == TOKEN, failure)
        acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, perm, ident) for tag, perm, ident in
                                               ((1, 7, 0xFFFFFFFF), (2, 7, 4242), (4, 5, 0xFFFFFFFF), (0x10, 7, 0xFFFFFFFF), (0x20, 0, 0xFFFFFFFF)))
        real_acl = g._acl
        g._acl = lambda path, name: acl if name == g.ACL_ACCESS else None
        try:
            try:
                g.check_directory(os.path.join(root, str(UID)), UID)
                acl_msg = ""
            except g.TokenFileError as e:
                acl_msg = str(e)
        finally:
            g._acl = real_acl
        check("an ACL entry for another user that grants write after the mask is refused by the ACL check itself (the second line)", "grants write" in acl_msg, acl_msg)
        mi = os.path.join(base, "mountinfo")
        with open(mi, "w") as fh:
            fh.write("1 0 0:1 / / rw - ext4 /dev/a rw\n2 1 0:2 / /srv/with\\040space rw - xfs /dev/b rw\n3 1 0:3 / /srv/with\\040space rw - tmpfs tmpfs rw\n4 1 0:4 / /srv/tab\\011and\\134slash rw - btrfs /dev/c rw\n")
        check("the mount table: an escaped space is decoded, and of two mounts on one point the later is the visible one",
              g.filesystem_of("/srv/with space/x", mi) == "tmpfs" and g.filesystem_of("/etc", mi) == "ext4")
        check("…and every octal escape of the mount point (a tab, a backslash), not only the space",
              g.filesystem_of("/srv/tab\tand\\slash/x", mi) == "btrfs")

        print("remove")
        root = fresh(base, "r")
        write(root)
        check("the file goes when the store holds no token; a second time is absent", (g.remove(UID, root), g.remove(UID, root)) == ("removed", "absent"))

    print("test_gateway_token:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
