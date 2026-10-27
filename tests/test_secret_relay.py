#!/usr/bin/env python3
"""tools/fabric/secret_relay.py (`fabric-secrets relay`, ADR-034 §7 step 1): the relay's database
copied to Proton Drive and read back. A scratch account (keyring outside the scratch HOME, as
tests/test_secret_store.py says), a fixture sqlite database in WAL mode, and a fake proton-drive
on PATH that keeps each upload as a numbered revision; never the live relay or the real Drive."""
from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_relay.py")
STORE_TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
sys.path.insert(0, os.path.dirname(STORE_TOOL))
import secret_store  # noqa: E402 — the id helpers
from instance_fixtures import write_secrets_instance, own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

FAKE = r'''#!/usr/bin/env python3
import os, shutil, sys, time
D = %r
a = [x for x in sys.argv[1:] if x != "-t"]
cmd, rest = a[:2], a[2:]
loc = lambda p: os.path.join(D, p.lstrip("/"))
flag = lambda n: os.path.exists(os.path.join(D, "..", n))
if flag("no-session") and cmd != ["filesystem", "download"]:
    print("Error: session expired, please log in", file=sys.stderr); sys.exit(1)
if cmd == ["filesystem", "info"]:
    sys.exit(0 if os.path.exists(loc(rest[0])) else 1)
elif cmd == ["filesystem", "create-folder"]:
    os.makedirs(os.path.join(loc(rest[0]), rest[1]))
elif cmd == ["filesystem", "upload"]:
    if flag("fail-upload"):
        print("Error: upload failed", file=sys.stderr); sys.exit(1)
    if flag("slow-upload"):
        open(os.path.join(D, "..", "slow-started"), "w").close(); time.sleep(60)
    if rest[:2] != ["-f", "create-new-revision"]: sys.exit(3)   # a new revision, never a replacement
    rest = rest[2:]
    open(os.path.join(D, "..", "at-upload"), "a").write("\n".join(n for _, _, fs in os.walk(os.environ["TMPDIR"]) for n in fs) + "\n")
    dst = os.path.join(loc(rest[1]), os.path.basename(rest[0]))
    shutil.copy(rest[0], dst)
    open(os.path.join(D, "..", "revisions"), "a").write(os.path.basename(rest[0]) + "\n")
elif cmd == ["filesystem", "download"]:
    rest = [x for x in rest if x not in ("-f", "remove")]
    if not os.path.exists(loc(rest[0])): sys.exit(1)
    shutil.copy(loc(rest[0]), os.path.join(rest[1], os.path.basename(rest[0])))
else:
    sys.exit(9)
'''

WRITER = r'''
import sqlite3, sys, time
con = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=30)
n = 0
while True:
    n += 1
    con.execute("BEGIN")
    con.execute("INSERT INTO a VALUES (?, ?)", (n, "x" * 400))
    con.execute("INSERT INTO b VALUES (?, ?)", (n, "y" * 400))
    con.execute("COMMIT")
    if n == 50:
        open(sys.argv[2], "w").close()
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_secret_relay.") as tmp:
        home, gnupg, fabric, scratch = (os.path.join(tmp, d) for d in ("home", "gnupg", "fabric", "scratch"))
        drive = os.path.join(tmp, "drive", "d")
        store = os.path.join(home, "store")
        for d in (home, scratch, os.path.join(drive, "my-files")):
            os.makedirs(d)
        os.makedirs(gnupg, mode=0o700)
        os.makedirs(os.path.join(fabric, "projects"))
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        write_secrets_instance(fabric)
        fake = os.path.join(tmp, "bin", "proton-drive")
        os.makedirs(os.path.dirname(fake))
        with open(fake, "w") as fh:
            fh.write(FAKE % drive)
        os.chmod(fake, 0o755)
        flags = os.path.dirname(drive)
        state = os.path.join(tmp, "state")
        logfile = os.path.join(state, "agents", subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(),
                               "relay-backup.jsonl")
        env = {"PATH": f"{os.path.dirname(fake)}:/usr/bin:/bin", "HOME": home, "GNUPGHOME": gnupg, "LANG": "C.UTF-8",
               "TMPDIR": scratch, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_SECRET_STORE": store,
               "AGENT_FABRIC_STATE_DIR": state, "GIT_CONFIG_GLOBAL": os.path.join(home, ".gitconfig"),
               "GIT_CONFIG_NOSYSTEM": "1"}

        def relay(*args: str, **kw) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *args], env={**env, **kw.get("env", {})}, cwd=tmp,
                                  capture_output=True, text=True, timeout=300)

        def scratch_left() -> list[str]:
            return sorted(os.listdir(scratch))

        def blob_path() -> str:
            return os.path.join(drive, "my-files", "agent-fabric", "relay", "claude-bridge.db.gz.gpg")

        def flag(name: str, on: bool) -> None:
            p = os.path.join(flags, name)
            if on:
                open(p, "w").close()
            elif os.path.exists(p):
                os.remove(p)

        aid = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        p = subprocess.run([sys.executable, STORE_TOOL, "init", "--agent-id", aid], env=env, capture_output=True, text=True, timeout=300)
        check("a scratch store to encrypt to", p.returncode == 0, p.stderr)

        db = os.path.join(tmp, "relay", "claude-bridge.db")
        os.makedirs(os.path.dirname(db))
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE a (n INTEGER PRIMARY KEY, v TEXT)")
        con.execute("CREATE TABLE b (n INTEGER PRIMARY KEY, v TEXT)")
        con.commit()
        con.close()

        # A writer commits pairs (a row in each table per transaction) without pause. A consistent
        # snapshot has as many rows in a as in b; a file copied in pieces while it runs does not.
        started = os.path.join(tmp, "writer-started")
        writer = subprocess.Popen([sys.executable, "-c", WRITER, db, started])
        try:
            for _ in range(200):
                if os.path.exists(started):
                    break
                time.sleep(0.05)
            check("a writer is committing to the fixture database", os.path.exists(started))
            p = relay("backup", "--db", db)
            check("backup with the writer running: exit 0, one line, sizes named",
                  p.returncode == 0 and len(p.stdout.splitlines()) == 1 and p.stdout.startswith("relay backup:") and p.stderr == "",
                  p.stdout + p.stderr)
        finally:
            writer.kill()
            writer.wait()
        check("…the scratch directory holds nothing afterwards", scratch_left() == [], scratch_left())
        revs = os.path.join(flags, "revisions")
        check("…one blob and one manifest went up, under the fixed names",
              open(revs).read().split() == ["claude-bridge.db.gz.gpg", "claude-bridge.manifest.json"], open(revs).read())
        lines = open(logfile).read().splitlines() if os.path.exists(logfile) else []
        check("…and the manifest line (time, sha256, size) is kept locally", len(lines) == 1
              and set(json.loads(lines[0])) == {"at", "sha256", "size"}, lines)
        at_upload = open(os.path.join(flags, "at-upload")).read().split()
        check("…at upload the scratch held the encrypted blob and the manifest, no plain or gzipped snapshot (disk peak)",
              sorted(at_upload[:2]) == ["claude-bridge.db.gz.gpg", "claude-bridge.manifest.json"], at_upload)
        check("…the blob on the Drive is ciphertext: no sqlite header, no gzip header",
              not open(blob_path(), "rb").read(64).startswith((b"SQLite format 3", b"\x1f\x8b")))

        dest = os.path.join(tmp, "restored")
        p = relay("restore", dest)
        check("restore into an absent directory: exit 0, claude-bridge.db and nothing else", p.returncode == 0
              and os.listdir(dest) == ["claude-bridge.db"] and oct(os.stat(os.path.join(dest, "claude-bridge.db")).st_mode & 0o777) == "0o600",
              p.stdout + p.stderr)
        r = sqlite3.connect(os.path.join(dest, "claude-bridge.db"))
        ok, na, nb = r.execute("PRAGMA integrity_check").fetchone()[0], *(r.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in "ab")
        r.close()
        check("…the copy passes integrity_check and is consistent (a == b, not empty)", ok == "ok" and na == nb and na > 0, (ok, na, nb))
        check("…restore leaves no -wal or -shm beside the copy and nothing in scratch",
              os.listdir(dest) == ["claude-bridge.db"] and scratch_left() == [])

        # The control: the oracle above must be able to fail. Rows committed after the last checkpoint
        # live only in the -wal; a copy of the main file alone misses them, the online backup does not.
        wdb = os.path.join(tmp, "relay-w", "claude-bridge.db")
        os.makedirs(os.path.dirname(wdb))
        hold = sqlite3.connect(wdb)
        hold.execute("PRAGMA journal_mode=WAL")
        hold.execute("PRAGMA wal_autocheckpoint=0")
        hold.execute("CREATE TABLE a (n INTEGER PRIMARY KEY, v TEXT)")
        hold.commit()
        hold.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for i in range(40):
            hold.execute("INSERT INTO a VALUES (?, 'x')", (i,))
            hold.commit()
        plain = os.path.join(tmp, "plain-copy.db")
        shutil.copy(wdb, plain)
        pc = sqlite3.connect(plain)
        try:
            seen = pc.execute("SELECT count(*) FROM a").fetchone()[0]
        except sqlite3.Error:
            seen = -1
        pc.close()
        check("control: a plain copy of the main file, WAL not checkpointed, misses committed rows", seen < 40, seen)
        p = relay("backup", "--db", wdb)
        dest2 = os.path.join(tmp, "restored-w")
        q = relay("restore", dest2)
        r = sqlite3.connect(os.path.join(dest2, "claude-bridge.db")) if q.returncode == 0 else None
        got = r.execute("SELECT count(*) FROM a").fetchone()[0] if r else -1
        check("…the online backup of the same database holds all 40 (and the writer's connection was still open)",
              p.returncode == 0 and got == 40, (p.stderr, q.stderr, got))
        if r:
            r.close()
        hold.close()

        # A WAL database with no -wal/-shm beside it (the relay stopped cleanly): the read-only open must still work.
        cold = os.path.join(tmp, "relay-cold", "claude-bridge.db")
        os.makedirs(os.path.dirname(cold))
        c = sqlite3.connect(cold)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE a (n INTEGER)")
        c.execute("INSERT INTO a VALUES (1)")
        c.commit()
        c.close()
        check("fixture: the cold database has no wal or shm", sorted(os.listdir(os.path.dirname(cold))) == ["claude-bridge.db"],
              os.listdir(os.path.dirname(cold)))
        cold_bytes = open(cold, "rb").read()
        p = relay("backup", "--db", cold)
        # sqlite's read-only open leaves empty -wal/-shm beside the file; the database itself is not touched.
        check("a WAL database with no wal/shm files backs up, and its main file is byte for byte as it was",
              p.returncode == 0 and open(cold, "rb").read() == cold_bytes, p.stderr)

        p = relay("backup", "--verify")
        check("backup --verify: the latest revision decrypts, matches the manifest, passes integrity_check",
              p.returncode == 0 and "decrypts" in p.stdout and scratch_left() == [], p.stdout + p.stderr)

        # Restore refusals: nothing written, nothing changed.
        full = os.path.join(tmp, "not-empty")
        os.makedirs(full)
        open(os.path.join(full, "keep"), "w").write("mine")
        for label, target in (("a directory with a file in it", full), ("a regular file", os.path.join(full, "keep"))):
            q = relay("restore", target)
            check(f"restore into {label}: refused in one line, exit 1, nothing written",
                  q.returncode == 1 and "not an empty directory" in q.stderr and len(q.stderr.splitlines()) == 1
                  and os.listdir(full) == ["keep"] and open(os.path.join(full, "keep")).read() == "mine", q.stderr)
        link = os.path.join(tmp, "link-to-empty")
        emp = os.path.join(tmp, "an-empty-dir")
        os.makedirs(emp)
        os.symlink(emp, link)
        q = relay("restore", link)
        check("restore into a symlink to an empty directory: refused", q.returncode == 1 and os.listdir(emp) == [], q.stderr)
        q = relay("restore", os.path.join(tmp, "restored-w"))
        check("restore into the earlier restore (not empty): refused, the copy untouched",
              q.returncode == 1 and os.listdir(os.path.join(tmp, "restored-w")) == ["claude-bridge.db"], q.stderr)

        # A damaged or mismatched revision is a refusal, never a database.
        good_blob = open(blob_path(), "rb").read()
        manifest_path = os.path.join(os.path.dirname(blob_path()), "claude-bridge.manifest.json")
        good_manifest = open(manifest_path).read()
        bad = bytearray(good_blob)
        bad[len(bad) // 2] ^= 0xFF
        open(blob_path(), "wb").write(bytes(bad))
        d3 = os.path.join(tmp, "restored-bad")
        q = relay("restore", d3)
        v = relay("backup", "--verify")
        check("a damaged blob: restore refused, no directory made; verify exits 1 in one line",
              q.returncode == 1 and not os.path.exists(d3) and v.returncode == 1 and len(v.stderr.splitlines()) == 1
              and "Traceback" not in q.stderr + v.stderr and scratch_left() == [], (q.stderr, v.stderr))
        open(blob_path(), "wb").write(good_blob)
        m = json.loads(good_manifest)
        m["sha256"] = "0" * 64
        open(manifest_path, "w").write(json.dumps(m) + "\n")
        q = relay("restore", d3)
        check("a manifest whose sha256 is not the blob's: restore refused naming the manifest, nothing written",
              q.returncode == 1 and "manifest" in q.stderr and not os.path.exists(d3), q.stderr)
        os.remove(manifest_path)
        q = relay("restore", d3)
        check("no manifest on the Drive: refused", q.returncode == 1 and not os.path.exists(d3), q.stderr)
        open(manifest_path, "w").write(good_manifest)
        q = relay("restore", d3)
        check("…and the repaired revision restores (the refusals' control)", q.returncode == 0 and os.listdir(d3) == ["claude-bridge.db"], q.stderr)

        # Backup refusals: one line, exit 1, nothing left, nothing uploaded.
        before = open(revs).read()
        garbage = os.path.join(tmp, "garbage.db")
        open(garbage, "wb").write(b"this is not a database" * 100)
        linked = os.path.join(tmp, "linked.db")
        os.symlink(db, linked)
        # Opens, reads and copies, yet integrity_check says no: an index whose pages the schema forgot.
        broken = os.path.join(tmp, "broken.db")
        bc = sqlite3.connect(broken)
        bc.execute("CREATE TABLE t (n INTEGER, v TEXT)")
        bc.executemany("INSERT INTO t VALUES (?, ?)", [(i, "z" * 50) for i in range(500)])
        bc.execute("CREATE INDEX t_v ON t (v)")
        bc.commit()
        bc.execute("PRAGMA writable_schema=1")
        bc.execute("DELETE FROM sqlite_master WHERE name='t_v'")
        bc.commit()
        bc.close()
        bc = sqlite3.connect(broken)
        said = bc.execute("PRAGMA integrity_check").fetchone()[0]
        bc.close()
        check("fixture: the broken database is readable but fails its own integrity check", said != "ok", said)
        for label, args in (("a database that fails integrity_check", ["--db", broken]), ("no database", ["--db", os.path.join(tmp, "absent.db")]), ("a file that is not sqlite", ["--db", garbage]),
                            ("a symlink", ["--db", linked]), ("a directory", ["--db", tmp])):
            q = relay("backup", *args)
            check(f"backup of {label}: one line, exit 1, nothing uploaded, scratch empty",
                  q.returncode == 1 and len(q.stderr.splitlines()) == 1 and "Traceback" not in q.stderr
                  and open(revs).read() == before and scratch_left() == [], q.stderr)
        for fl, expect in (("no-session", "session has lapsed"), ("fail-upload", "upload failed")):
            flag(fl, True)
            q = relay("backup", "--db", db)
            flag(fl, False)
            check(f"backup with {fl}: one line naming the cause, exit 1, scratch empty, no manifest line kept",
                  q.returncode == 1 and expect in q.stderr and len(q.stderr.splitlines()) == 1 and scratch_left() == []
                  and len(open(logfile).read().splitlines()) == 3, q.stderr)
        q = relay("backup", "--db", db, env={"PATH": "/usr/bin:/bin"})
        check("no proton-drive on PATH: one line, exit 1, scratch empty",
              q.returncode == 1 and "not installed" in q.stderr and scratch_left() == [], q.stderr)

        # A stopped timer (SIGTERM) removes the plain-text snapshot with it.
        flag("slow-upload", True)
        pr = subprocess.Popen([sys.executable, TOOL, "backup", "--db", db], env=env, cwd=tmp, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        for _ in range(300):
            if os.path.exists(os.path.join(flags, "slow-started")):
                break
            time.sleep(0.1)
        mid = scratch_left()
        pr.send_signal(signal.SIGTERM)
        try:
            pr.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            pr.kill()
            pr.communicate()
        flag("slow-upload", False)
        check("control: mid-upload the scratch directory holds the snapshot", len(mid) == 1, mid)
        check("SIGTERM mid-upload: exits non-zero and the scratch directory is empty", pr.returncode not in (0, None) and scratch_left() == [],
              (pr.returncode, scratch_left()))

        # The owner's recovery key opens it when this login's key cannot.
        rhome = os.path.join(tmp, "recovery-gnupg")
        os.makedirs(rhome, mode=0o700)
        rg = ["gpg", "--homedir", rhome, "--batch", "--pinentry-mode", "loopback", "--passphrase", "pw"]
        subprocess.run(rg + ["--quick-gen-key", "agent-fabric recovery <recovery@agents.agent-fabric>", "ed25519", "cert", "never"],
                       check=True, capture_output=True)
        rfpr = [l.split(":")[9] for l in subprocess.run(["gpg", "--homedir", rhome, "--with-colons", "--list-keys"],
                capture_output=True, text=True).stdout.splitlines() if l.startswith("fpr:")][0]
        subprocess.run(rg + ["--quick-add-key", rfpr, "cv25519", "encr", "never"], check=True, capture_output=True)
        with open(os.path.join(fabric, "identities", "recovery.asc"), "w") as fh:
            fh.write(subprocess.run(["gpg", "--homedir", rhome, "--armor", "--export", rfpr], capture_output=True, text=True).stdout)
        p = relay("backup", "--db", db)
        opened = subprocess.run(rg + ["--decrypt", blob_path()], capture_output=True)
        check("with identities/recovery.asc: the recovery key alone decrypts the blob to a gzip stream",
              p.returncode == 0 and opened.returncode == 0 and opened.stdout[:2] == b"\x1f\x8b", (p.stderr, opened.stderr[-200:]))
        check("…and the operator's own restore still works", relay("restore", os.path.join(tmp, "restored-r")).returncode == 0)
        check("each successful run was a new revision of the same two names",
              set(open(revs).read().split()) == {"claude-bridge.db.gz.gpg", "claude-bridge.manifest.json"}
              and len(open(revs).read().split()) >= 8, open(revs).read())
        check("no run left anything in scratch", scratch_left() == [], scratch_left())

    print("fail" if fails else "pass", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
