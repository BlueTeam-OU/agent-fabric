#!/usr/bin/env python3
"""pool.json is written by more than one thread of agentd (pool-add is an
action that starts in a thread of its own, pool-claim is answered inline) and
by more than one process; every read-modify-write runs under flock on
pool.json.lock (tools/fabric/control/pool.py `_locked`). Each race here is
made certain by slowing the read inside the critical section, not left to
timing; a refusal has its positive control. The port's own cases, frozen
against the Node, are tests/test_control_pool.py and run unchanged."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import pool as cp  # noqa: E402

HOLDER = "h/user"
KNOWN = {"python-dev"}
ARGS = {"role": "python-dev", "title": "t"}

HOLD_LOCK = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("held", flush=True)
sys.stdin.read()
"""


class Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="pool-race-")
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.file = os.path.join(self.dir, "pool.json")

    def add(self, sender: str = HOLDER) -> dict:
        return cp.pool_add({"from": sender, "to": [HOLDER], "args": dict(ARGS)}, me=HOLDER, holder=HOLDER, file=self.file,
                           known=KNOWN, now=lambda: "2026-10-30T00:00:00Z")

    def claim(self, sender: str, pid: str = "p1") -> dict:
        return cp.pool_claim({"from": sender, "args": {"id": pid}}, me=HOLDER, holder=HOLDER, file=self.file,
                             role_of=lambda a: {"role": "python-dev"})

    def raw(self) -> bytes:
        with open(self.file, "rb") as fh:
            return fh.read()

    def slow_reads(self) -> None:
        real = cp.read_pool

        def slow(file):
            doc = real(file)
            time.sleep(0.05)   # the window an unlocked read-modify-write loses an update in
            return doc
        cp.read_pool = slow
        self.addCleanup(setattr, cp, "read_pool", real)

    def run_threads(self, fns) -> list:
        out: list = [None] * len(fns)

        def go(i, fn):
            out[i] = fn()
        ts = [threading.Thread(target=go, args=(i, fn)) for i, fn in enumerate(fns)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        return out


class Races(Case):
    def test_simultaneous_adds_are_all_kept_with_their_own_ids(self):
        self.slow_reads()
        rs = self.run_threads([self.add] * 6)
        self.assertEqual([r["status"] for r in rs], ["added"] * 6)
        self.assertEqual(sorted(r["job"]["id"] for r in rs), [f"p{n}" for n in range(1, 7)])
        self.assertEqual(len(cp.read_pool(self.file)["jobs"]), 6)
        self.assertEqual(cp.read_pool(self.file)["seq"], 6)

    def test_two_claimants_of_one_job_never_both_get_it(self):
        self.add()
        self.slow_reads()
        a, b = self.run_threads([lambda: self.claim("h/a"), lambda: self.claim("h/b")])
        self.assertEqual(sorted([a["status"], b["status"]]), ["claimed", "refused"])
        loser = a if a["status"] == "refused" else b
        self.assertIn("is claimed by", loser["reason"])

    def test_an_add_and_a_claim_together_lose_neither(self):
        self.add()
        self.slow_reads()
        a, b = self.run_threads([self.add, lambda: self.claim("h/a")])
        self.assertEqual((a["status"], b["status"]), ("added", "claimed"))
        doc = cp.read_pool(self.file)
        self.assertEqual(len(doc["jobs"]), 2)
        self.assertEqual(doc["jobs"][0]["claimed"]["by"], "h/a")

    def test_two_writes_in_flight_do_not_share_a_temporary_name(self):
        both = threading.Barrier(2, timeout=10)
        real = os.replace

        def meet(src, dst):
            both.wait()   # both temporaries exist at once
            real(src, dst)
        os.replace = meet
        self.addCleanup(setattr, os, "replace", real)
        errs = []

        def w(n):
            try:
                cp._write_pool(self.file, {"seq": n, "jobs": []})
            except BaseException as e:   # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=w, args=(n,)) for n in (1, 2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(errs, [])
        self.assertEqual(sorted(os.listdir(self.dir)), ["pool.json"], "no temporary left behind")


class OtherProcess(Case):
    def hold(self):
        p = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, self.file + ".lock"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True, env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual(p.stdout.readline().strip(), "held")

        def release():
            p.stdin.close()
            p.wait(timeout=30)
            p.stdout.close()
        self.addCleanup(release)
        return release

    def test_a_lock_another_process_holds_is_a_refusal_and_changes_nothing_then_it_goes(self):
        self.assertEqual(self.add()["status"], "added")
        before = self.raw()
        saved = cp.POOL_LOCK_WAIT_S
        cp.POOL_LOCK_WAIT_S = 0.2
        self.addCleanup(setattr, cp, "POOL_LOCK_WAIT_S", saved)
        release = self.hold()
        for r in (self.add(), self.claim("h/a")):
            self.assertEqual(r["status"], "refused")
            self.assertIn("locked by another writer", r["reason"])
        self.assertEqual(self.raw(), before)
        release()
        self.assertEqual(self.add()["status"], "added", "positive control: the same call once the holder is gone")

    def test_a_lock_file_that_is_a_symlink_is_refused_not_followed(self):
        os.symlink("/dev/null", self.file + ".lock")
        r = self.add()
        self.assertEqual(r["status"], "refused")
        self.assertIn("cannot be locked", r["reason"])
        self.assertFalse(os.path.exists(self.file))


if __name__ == "__main__":
    unittest.main()
