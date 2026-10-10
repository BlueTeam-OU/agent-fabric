#!/usr/bin/env python3
"""Account persistence on a volatile root: the boot script
(runtime/provisioning/platform/qubes/agent-fabric-accounts.rc) and the
snapshot writer (tools/fabric/provisioning/persist_accounts.py), against a
scratch /etc, snapshot dir and a fake loginctl. Ported from
runtime/provisioning/platform/test_qubes-accounts.sh (ADR-040 Wave 6),
case for case.

What this holds still: the boot script appends every snapshotted record a
fresh /etc lacks, verbatim, never duplicates one already there, skips a
uid or gid the template has meanwhile taken and says so, and enables
linger for each re-added login; the writer replaces or appends one line
per login per file, is idempotent, installs the boot script once, and on
a persistent platform writes no snapshot and only enables linger. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import fcntl
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC = os.path.join(ROOT, "runtime", "provisioning", "platform", "qubes", "agent-fabric-accounts.rc")
WRITER = os.path.join(ROOT, "tools", "fabric", "provisioning", "persist_accounts.py")
TMPFILES = os.path.join(ROOT, "runtime", "provisioning", "platform", "agent-fabric.tmpfiles.conf")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        for d in ("etc", "snap", "rcd", "bin"):
            os.makedirs(f"{t}/{d}")
        log = f"{t}/loginctl.log"

        def put(path: str, text: str, mode: str = "w") -> None:
            with open(path, mode, encoding="utf-8") as fh:
                fh.write(text)

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def lines(path: str) -> list[str]:
            return read(path).splitlines()

        def mode_of(path: str) -> str:
            try:
                return oct(os.stat(path).st_mode & 0o7777)[2:]
            except OSError:
                return "absent"

        put(f"{t}/bin/loginctl", '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "${LOGINCTL_LOG:?}"\n')
        os.chmod(f"{t}/bin/loginctl", 0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env.update(LOGINCTL_LOG=log, AGENT_FABRIC_ETC=f"{t}/etc", AGENT_FABRIC_ACCOUNTS_SNAPSHOT=f"{t}/snap",
                   AGENT_FABRIC_RC_LOCAL_D=f"{t}/rcd", AGENT_FABRIC_LOGINCTL=f"{t}/bin/loginctl",
                   AGENT_FABRIC_LEASES=f"{t}/run/lock/agent-fabric", AGENT_FABRIC_TMPFILES_D=f"{t}/tmpfiles.d")

        def run(argv: list[str], **extra: str) -> tuple[int, str, str]:
            r = subprocess.run(argv, env={**env, **extra}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               timeout=120)
            return r.returncode, r.stdout, r.stderr

        # A boot's /etc: the template's users, none of ours.
        put(f"{t}/etc/passwd", "root:x:0:0:root:/root:/bin/bash\nuser:x:1000:1000::/home/user:/bin/bash\n")
        put(f"{t}/etc/shadow", "root:*:1:0:99999:7:::\nuser:*:1:0:99999:7:::\n")
        put(f"{t}/etc/group", "root:x:0:\nuser:x:1000:\notscache:x:990:user\n")
        put(f"{t}/etc/gshadow", "root:::\nuser:::\n")
        put(f"{t}/etc/subuid", "user:100000:65536\n")
        put(f"{t}/etc/subgid", "user:100000:65536\n")
        # The snapshot: two fabric accounts, one of which collides with a
        # template uid.
        put(f"{t}/snap/passwd", "db-admin:x:1004:1004:agent-fabric db-admin:/home/db-admin:/bin/bash\n"
                                "brand-comms-01:x:1000:1014:agent-fabric brand-comms:/home/brand-comms-01:/bin/bash\n")
        put(f"{t}/snap/shadow", "db-admin:$6$hash:20000:0:99999:7:::\nbrand-comms-01:$6$hash2:20000:0:99999:7:::\n")
        put(f"{t}/snap/group", "db-admin:x:1004:\nbrand-comms-01:x:1014:\n")
        put(f"{t}/snap/gshadow", "db-admin:!::\n")
        put(f"{t}/snap/subuid", "db-admin:200000:65536\nbrand-comms-01:300000:65536\n")
        shutil.copy(f"{t}/snap/subuid", f"{t}/snap/subgid")
        put(f"{t}/snap/members", "db-admin:otscache,nosuchgroup\nbrand-comms-01:otscache\nweb-dev-02:otscache\n")
        # A third whose uid is free but whose primary gid the template gave
        # to another group.
        put(f"{t}/snap/passwd", "web-dev-02:x:1009:990:agent-fabric web-dev:/home/web-dev-02:/bin/bash\n", "a")
        put(f"{t}/snap/shadow", "web-dev-02:$6$hash3:20000:0:99999:7:::\n", "a")
        put(f"{t}/snap/group", "web-dev-02:x:990:\n", "a")

        print("boot script: re-adds what /etc lacks, verbatim, and enables linger")
        rc, _, err = run(["sh", RC])
        check("exits 0", rc == 0, err)
        check("the lease directory is made, 1777 (bin/fabric-lease)", mode_of(f"{t}/run/lock/agent-fabric") == "1777",
              mode_of(f"{t}/run/lock/agent-fabric"))
        check("passwd line appended verbatim",
              "db-admin:x:1004:1004:agent-fabric db-admin:/home/db-admin:/bin/bash" in lines(f"{t}/etc/passwd"),
              read(f"{t}/etc/passwd"))
        check("shadow line appended verbatim", "db-admin:$6$hash:20000:0:99999:7:::" in lines(f"{t}/etc/shadow"),
              read(f"{t}/etc/shadow"))
        check("group and gshadow appended",
              "db-admin:x:1004:" in lines(f"{t}/etc/group") and "db-admin:!::" in lines(f"{t}/etc/gshadow"))

        def starts(path: str, prefix: str) -> bool:
            return any(line.startswith(prefix) for line in lines(path))
        check("a uid the template took is skipped, loudly",
              not starts(f"{t}/etc/passwd", "brand-comms-01:") and "uid 1000 is taken" in err, err)
        check("…and none of its other records go in",
              not any(starts(f"{t}/etc/{f}", "brand-comms-01:") for f in ("shadow", "group", "subuid", "subgid")))
        check("a gid the template gave another group skips the login whole, loudly",
              not any(starts(f"{t}/etc/{f}", "web-dev-02:") for f in ("passwd", "shadow", "group"))
              and "gid 990 is taken" in err, err)
        check("…no membership, no linger for it", "web-dev-02" not in read(f"{t}/etc/group") and "web-dev-02" not in read(log))
        check("subuid and subgid appended",
              "db-admin:200000:65536" in lines(f"{t}/etc/subuid") and "db-admin:200000:65536" in lines(f"{t}/etc/subgid"))
        check("supplementary group membership restored (members)",
              "otscache:x:990:user,db-admin" in lines(f"{t}/etc/group"), read(f"{t}/etc/group"))
        check("…not for the skipped login", "brand-comms-01" not in read(f"{t}/etc/group"))
        check("…and a group the boot lacks is left alone", "nosuchgroup" not in read(f"{t}/etc/group"))
        check("linger enabled for the re-added login only",
              "enable-linger db-admin" in lines(log) and "brand-comms-01" not in read(log), read(log))
        check("the template's own lines untouched",
              sum(1 for ln in lines(f"{t}/etc/passwd") if ln.startswith("user:")) == 1
              and sum(1 for ln in lines(f"{t}/etc/passwd") if ln.startswith("root:")) == 1)
        n1 = len(lines(f"{t}/etc/passwd"))
        run(["sh", RC])
        check("a second boot appends nothing twice", n1 == len(lines(f"{t}/etc/passwd"))
              and sum(1 for ln in lines(f"{t}/etc/passwd") if ln.startswith("db-admin:")) == 1)
        check("…nor a membership twice", "otscache:x:990:user,db-admin" in lines(f"{t}/etc/group"), read(f"{t}/etc/group"))
        put(log, "")
        shutil.rmtree(f"{t}/snap")
        shutil.rmtree(f"{t}/run")
        rc, _, _ = run(["sh", RC])
        check("no snapshot: nothing done, exit 0", rc == 0 and not read(log))
        check("…but the lease directory is made even then", os.path.isdir(f"{t}/run/lock/agent-fabric"))
        # install absent: mkdir+chmod gives the same mode; both failing is
        # said on stderr.
        noinstall = f"{t}/noinstall"
        os.makedirs(noinstall)
        for tool in ("mkdir", "chmod", "sh", "grep", "cut", "awk", "cp", "mv", "rm", "tr", "head", "paste", "cat", "printf"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, f"{noinstall}/{tool}")
        shutil.rmtree(f"{t}/run")
        run(["sh", RC], PATH=noinstall)
        check("without install(1) the fallback still makes it 1777", mode_of(f"{t}/run/lock/agent-fabric") == "1777",
              mode_of(f"{t}/run/lock/agent-fabric"))
        rc, _, err = run(["sh", "-c", 'chmod() { return 1; }; . "$0"', RC], PATH=noinstall,
                         AGENT_FABRIC_LEASES=f"{t}/nowhere/deep/leases")
        check("a fallback that cannot set the mode says so", "not made 1777" in err, err)

        print("writer: one line per login per file, replace-or-append, the boot script installed once")
        os.makedirs(f"{t}/snap")
        put(log, "")
        # A live /etc with our accounts present (the writer reads from it).
        put(f"{t}/etc/passwd", "edge-hosting:x:1011:1011:agent-fabric edge-hosting:/home/edge-hosting:/bin/bash\n", "a")
        put(f"{t}/etc/shadow", "edge-hosting:$6$eh:20001:0:99999:7:::\n", "a")
        put(f"{t}/etc/group", "edge-hosting:x:1011:\n", "a")
        put(f"{t}/etc/group", read(f"{t}/etc/group").replace("otscache:x:990:user,db-admin\n",
                                                             "otscache:x:990:user,db-admin,edge-hosting\n"))
        # The platform: the Qubes profile (volatile root); detect.sh honours
        # the override.
        env["AGENT_FABRIC_PLATFORM"] = "fedora-qubes"
        rc, out, err = run([sys.executable, "-I", WRITER, "db-admin", "edge-hosting"])
        check("exits 0", rc == 0, out + err)
        check("the live passwd line is snapshotted",
              "edge-hosting:x:1011:1011:agent-fabric edge-hosting:/home/edge-hosting:/bin/bash" in lines(f"{t}/snap/passwd"),
              read(f"{t}/snap/passwd"))
        check("…and shadow", "edge-hosting:$6$eh:20001:0:99999:7:::" in lines(f"{t}/snap/shadow"))
        check("snapshot files 600 in a 700 directory",
              mode_of(f"{t}/snap/passwd") == "600" and mode_of(f"{t}/snap") == "700",
              f"{mode_of(f'{t}/snap')} {mode_of(f'{t}/snap/passwd')}")
        with open(f"{t}/snap/.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rc, out, err = run([sys.executable, "-I", WRITER, "db-admin"], AGENT_FABRIC_LOCK_WAIT="1")
        check("a second writer waits for the lock and says so when it does not come",
              rc != 0 and "locked by another writer" in out + err, out + err)
        with open(f"{t}/snap/.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            rc, out, err = run([sys.executable, "-I", WRITER, "db-admin"], AGENT_FABRIC_LOCK_WAIT="1")
        check("…and a writer is as much kept out by a reader's shared lock: the lock it takes is exclusive",
              rc != 0 and "locked by another writer" in out + err, out + err)
        check("the boot script is installed", os.access(f"{t}/rcd/agent-fabric-accounts.rc", os.X_OK))
        check("the lease directory made for this boot; no tmpfiles.d on a volatile /etc",
              os.path.isdir(f"{t}/run/lock/agent-fabric") and not os.path.exists(f"{t}/tmpfiles.d"))
        check("supplementary groups snapshotted (members)",
              "edge-hosting:otscache" in lines(f"{t}/snap/members") and "db-admin:otscache" in lines(f"{t}/snap/members"),
              read(f"{t}/snap/members"))
        put(f"{t}/rcd/agent-fabric-accounts.rc", "# stale\n")
        run([sys.executable, "-I", WRITER, "db-admin"])
        check("an installed boot script that differs is refreshed",
              filecmp.cmp(RC, f"{t}/rcd/agent-fabric-accounts.rc", shallow=False))
        hidden = [n for n in os.listdir(f"{t}/snap") if n.startswith(".") and n != ".lock"]
        check("no temporary file left in the snapshot", not hidden, " ".join(hidden))
        check("linger enabled for each",
              "enable-linger db-admin" in lines(log) and "enable-linger edge-hosting" in lines(log), read(log))
        put(f"{t}/etc/passwd", read(f"{t}/etc/passwd").replace(
            "edge-hosting:x:1011:1011:agent-fabric edge-hosting", "edge-hosting:x:1011:1011:renamed"))
        run([sys.executable, "-I", WRITER, "edge-hosting"])
        check("a changed line replaces the old one, never a second",
              sum(1 for ln in lines(f"{t}/snap/passwd") if ln.startswith("edge-hosting:")) == 1
              and "renamed" in read(f"{t}/snap/passwd"), read(f"{t}/snap/passwd"))
        check("other logins' lines kept", sum(1 for ln in lines(f"{t}/snap/passwd") if ln.startswith("db-admin:")) == 1)
        rc, out, err = run([sys.executable, "-I", WRITER, "no-such-login"])
        check("an unknown login is refused, named", rc != 0 and "no such account" in out + err, out + err)

        print("writer on a persistent platform: linger only, no snapshot")
        for d in ("snap", "rcd", "run"):
            shutil.rmtree(f"{t}/{d}", ignore_errors=True)
        put(log, "")
        env["AGENT_FABRIC_PLATFORM"] = "fedora"
        run([sys.executable, "-I", WRITER, "db-admin"])
        check("no snapshot written; linger enabled",
              not os.path.exists(f"{t}/snap") and not os.path.exists(f"{t}/rcd") and "enable-linger db-admin" in lines(log),
              read(log))
        conf = f"{t}/tmpfiles.d/agent-fabric.conf"
        check("the lease directory made now, and its tmpfiles.d entry installed for the next boot",
              os.path.isdir(f"{t}/run/lock/agent-fabric") and os.path.isfile(conf)
              and filecmp.cmp(TMPFILES, conf, shallow=False))
        check("…the entry says 1777, root, no age", "d /run/lock/agent-fabric 1777 root root -" in lines(conf), read(conf))

    print(f"\ntest_qubes_accounts_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
