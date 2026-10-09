#!/usr/bin/env python3
"""The control agent's machine and account extractors (tools/fabric/control/ops):
host, disk, the Claude accounts with their read lock, and presence. A port of
the second half of runtime/control/tests/ops.test.mjs, case for case; the rest
is tests/test_control_ops.py's."""
from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ops  # noqa: E402
import control.ops.util  # noqa: E402,F401
import control.ops.usage  # noqa: E402,F401 — the package's re-exports shadow these module names

util, usage_mod = sys.modules["control.ops.util"], sys.modules["control.ops.usage"]
_HOLD = tempfile.TemporaryDirectory(prefix="ops-hold-")
os.environ["AGENT_FABRIC_HOLD_DIR"] = _HOLD.name

ACCESS = "oauth-access-token-value-XYZ"
USAGE_EVENTS = json.dumps([
    {"type": "system", "subtype": "init", "model": "claude-opus-5-5"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Current session: 11% used"}]},
     "usage_report": {"rate_limits": {"limits": [
         {"kind": "session", "group": "session", "percent": 11, "resets_at": "2026-09-24T18:49:59Z", "scope": None},
         {"kind": "weekly_all", "group": "weekly", "percent": 83, "resets_at": "2026-09-28T15:59:59Z", "scope": None},
         {"kind": "weekly_scoped", "group": "weekly", "percent": 86, "resets_at": "2026-09-28T15:59:59Z", "scope": {"model": {"display_name": "Opus"}}}]}}},
    {"type": "result", "subtype": "success", "is_error": False, "num_turns": 0, "total_cost_usd": 0, "result": "Current session: 11% used"}])


def write(path: str, text: str = "", mode: str = "w") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(text)
    return path


def done(out: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, "")


class Base(unittest.TestCase):
    def scratch(self, prefix: str = "ops-") -> str:
        t = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(t.cleanup)
        return t.name


class Host(Base):
    def test_the_machine_from_a_scratch_proc_and_sys(self):
        root = self.scratch("ctl-host-")
        proc, sysd, leases = (os.path.join(root, n) for n in ("proc", "sys", "leases"))
        write(os.path.join(proc, "loadavg"), "3.37 3.44 3.22 5/1200 999\n")
        write(os.path.join(proc, "meminfo"), "MemTotal:       31563000 kB\nMemFree:         9750000 kB\nMemAvailable:   21901000 kB\nSwapTotal:       9437176 kB\nSwapFree:        9437176 kB\n")
        # two mounts of one device (/ and /usr/lib/modules) and one of another: two rows
        write(os.path.join(proc, "mounts"), "/dev/mapper/dmroot / ext4 rw 0 0\nnone /usr/lib/modules ext4 ro 0 0\n/dev/mapper/dmroot /usr/lib/modules ext4 ro 0 0\n/dev/xvdb /rw ext4 rw 0 0\ntmpfs /run tmpfs rw 0 0\n")
        xm = os.path.join(sysd, "devices", "system", "xen_memory", "xen_memory0")
        write(os.path.join(xm, "target_kb"), "31900000\n")
        write(os.path.join(xm, "info", "current_kb"), "31899000\n")
        write(os.path.join(leases, "backend-test"), "db-admin 4242 2026-09-19T08:26:43Z backend-test (suite)\n")
        write(os.path.join(leases, "free-one"), "user 1 2026-09-19T00:00:00Z free-one\n")
        write(os.path.join(leases, ".lock"), "")
        write(os.path.join(leases, "not a lease; $(id)"), "x 1 t n\n")   # outside fabric-lease's name grammar: never probed
        calls: list[list] = []

        def run(cmd, **kw):
            fd = int(cmd[3]) if cmd[0] == "flock" else None
            target = os.readlink(f"/proc/self/fd/{fd}") if fd is not None else None
            calls.append([*cmd, target])
            self.assertTrue(kw.get("timeout"), "every call is bounded")
            if cmd[0] == "xenstore-read":
                return done("31916000\n")
            if cmd[0] == "ps":
                return done("USER PID RSS COMMAND\nbackend-dev-02 667140 2191360 VBCSCompiler\np2p-network-dev-01 674834 159744 rustc\n")
            if cmd[0] == "flock":
                self.assertEqual(kw["pass_fds"], (fd,))
                return subprocess.CompletedProcess(cmd, 1 if target.endswith(("backend-test", "big-one")) else 0)
            raise FileNotFoundError(2, "No such file", cmd[0])

        def statfs(mnt):
            rw = mnt == "/rw"
            return types.SimpleNamespace(f_frsize=4096, f_blocks=77332480 if rw else 10485760, f_bavail=22020096 if rw else 5505024)
        # A fifo with no writer under a grammar-conforming name, and a symlink:
        # neither hangs the probe nor becomes a row (O_NONBLOCK, O_NOFOLLOW, fstat).
        os.mkfifo(os.path.join(leases, "a-fifo"))
        os.symlink(os.path.join(leases, "backend-test"), os.path.join(leases, "a-link"))
        # a record grown past the bound: only the first line's first 256 bytes are read
        write(os.path.join(leases, "big-one"), "db-admin 7 2026-09-19T00:00:00Z big-one" + " " * 5000 + "(late)\n" + "x" * 100000)
        before = len(os.listdir("/proc/self/fd"))
        h = ops.host(proc=proc, sys=sysd, leases=leases, run=run, cpus=6, statfs=statfs)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before, "every probed descriptor is closed, on the held path and the free path alike")
        self.assertEqual((h["status"], h["cpus"]), ("ok", 6))
        self.assertEqual(h["loadavg"], [3.37, 3.44, 3.22])
        self.assertEqual(h["mem_mb"], {"total": 30823, "available": 21388, "swap_total": 9216, "swap_free": 9216})
        self.assertEqual(h["balloon_mb"], {"current": 31151, "target": 31152, "static_max": 31168})
        self.assertEqual([d["mount"] for d in h["disk"]], ["/", "/rw"], "one row per block device, tmpfs and none excluded")
        self.assertEqual(h["disk"][1], {"mount": "/rw", "size_gb": 295, "avail_gb": 84, "use_pct": 72})
        self.assertEqual(h["leases"], [{"name": "backend-test", "holder": "db-admin", "pid": 4242, "since": "2026-09-19T08:26:43Z", "label": "suite"},
                                       {"name": "big-one", "holder": "db-admin", "pid": 7, "since": "2026-09-19T00:00:00Z", "label": None}],
                         "the held leases only; the free one, the dotfile, the fifo, the symlink and the name outside the grammar are not rows; the grown record is read bounded")
        flocks = [c for c in calls if c[0] == "flock"]
        self.assertFalse(any(str(c[-1]).endswith(("/a-fifo", "/a-link")) for c in flocks), "a fifo or a symlink never reaches flock")
        self.assertFalse(any("not a lease" in str(c[-1]) for c in flocks), "a name outside the grammar never reaches the probe")
        self.assertTrue(any(c[1:3] == ["-s", "-n"] and str(c[-1]).endswith("/backend-test") for c in flocks),
                        "the probe hands flock an already-open read-only descriptor and asks for a SHARED lock — no shell, no O_CREAT, never the exclusive lock a caller needs")
        # a file the probe cannot open is not a lease row, and flock is never asked about it
        os.chmod(os.path.join(leases, "free-one"), 0)
        if os.getuid() != 0:
            calls.clear()
            unreadable = ops.host(proc=proc, sys=sysd, leases=leases, run=run, cpus=6, statfs=statfs)
            self.assertFalse(any(str(c[-1]).endswith("/free-one") for c in calls), "an unopenable file never reaches flock")
            self.assertEqual([x["name"] for x in unreadable["leases"]], ["backend-test", "big-one"])
        os.chmod(os.path.join(leases, "free-one"), 0o644)
        # half a balloon in sysfs: the missing half is null, never 0
        os.unlink(os.path.join(xm, "info", "current_kb"))
        half = ops.host(proc=proc, sys=sysd, leases=leases, run=run, cpus=6, statfs=statfs)
        self.assertIsNone(half["balloon_mb"]["current"])
        self.assertEqual(half["balloon_mb"]["target"], 31152)
        self.assertEqual(h["top_rss"][0], {"user": "backend-dev-02", "pid": 667140, "rss_mb": 2140, "comm": "VBCSCompiler"})
        self.assertNotIn("/home/", json.dumps(h), "no path of a home in the record")

        def nothing(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        bare = ops.host(proc=proc, sys=os.path.join(root, "nosys"), leases=os.path.join(root, "noleases"), run=nothing, cpus=2, statfs=statfs)
        self.assertIsNone(bare["balloon_mb"])
        self.assertEqual((bare["leases"], bare["top_rss"]), ([], []), "not a Xen guest, no lease directory, no ps: null and empty, never a throw")
        self.assertIn("host", ops.OPS)

    def test_a_lease_naming_a_non_finite_pid_is_a_row_with_no_pid_not_a_failed_section(self):
        leases = self.scratch("leases-")
        for i, pid in enumerate(("Infinity", "-Infinity", "1e400", "NaN", "0")):
            write(os.path.join(leases, f"l{i}"), f"me {pid} 2026-10-09T00:00:00Z l{i}\n")
        held = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1)  # noqa: E731
        h = ops.host(proc="/nonexistent", sys="/nonexistent", leases=leases, run=held, cpus=1)
        self.assertEqual([x["pid"] for x in h["leases"]], [None] * 5)
        self.assertEqual(ops.collect("host", {"host_opts": {"proc": "/nonexistent", "sys": "/nonexistent", "leases": leases, "run": held, "cpus": 1}, "pressure_opts": {"file": os.path.join(leases, "none")}})["host"]["status"], "ok")

    def test_a_flock_that_cannot_run_or_hangs_is_not_a_held_lease(self):
        leases = self.scratch("leases-")
        write(os.path.join(leases, "one"), "u 1 t one\n")

        def hung(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 5)
        self.assertEqual(ops.host(proc="/nonexistent", sys="/nonexistent", leases=leases, run=hung, cpus=1)["leases"], [])


class Disk(Base):
    def test_the_own_home_in_one_scan_largest_entries_targets_a_partial_du_said_never_a_crash(self):
        home = self.scratch("disk-home-")
        for d in (".cache", ".local", "notes", "projects"):
            os.makedirs(os.path.join(home, d))
        write(os.path.join(home, ".bashrc"))
        P = lambda s: os.path.join(home, s)  # noqa: E731
        calls: list = []
        entries = [[400, ".cache"], [9000, ".local"], [4, ".bashrc"], [100, "notes"]]
        tree = [[50000, "projects"], [30000, "projects/a"], [20000, "projects/a/target"], [1000, "projects/a/target/target"],
                [12000, "projects/b/c"], [9000, "projects/b/c/target"], [5, "projects/target-notes"], [700, "projects/target"]]

        def out(rows):   # du -0: each record ends in NUL, a newline is part of a name
            return "".join(f"{kb}\t{P(rel)}\0" for kb, rel in rows).encode()

        def run(cmd, **kw):
            calls.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0, out(entries) if "-xsk" in cmd else out(tree), b"")
        d = ops.disk(home, run=run)
        self.assertEqual(d["status"], "ok", d)
        self.assertEqual([e["name"] for e in d["largest"]], ["projects", ".local", ".cache", "notes", ".bashrc"], "the largest first; projects counted by its own line")
        self.assertEqual(d["total_kb"], 50000 + 9000 + 400 + 100 + 4, "the total is the sum of the entries")
        self.assertEqual([(t["path"], t["kb"]) for t in d["targets"]], [("projects/a/target", 20000), ("projects/b/c/target", 9000), ("projects/target", 700)],
                         "every target/ to depth 3, largest first; one inside a target/ is not counted twice, a name only starting with target is not one")
        self.assertEqual(d["targets_kb"], 29700)
        self.assertTrue(all(c[0][0] == "du" and c[1]["timeout"] == ops.DISK_TIMEOUT_MS / 1000 and c[1]["max_bytes"] == ops.DISK_MAX_BUFFER for c in calls), calls)
        tree_call = next(c[0] for c in calls if "-xk" in c[0])
        self.assertEqual(tree_call[1:5], ["-0", "-xk", "--max-depth=3", "--"], "NUL-ended records")
        entries_call = next(c[0] for c in calls if "-xsk" in c[0])
        self.assertEqual(entries_call[1], "-0")
        self.assertNotIn(P("projects"), entries_call, "projects/ is not scanned twice")

        # A du that read part of a tree (exit 1) or stopped at its bound: what it
        # measured stands, the status says partial, errors say why.
        def partial_run(cmd, **kw):
            if "-xsk" in cmd:
                raise subprocess.CalledProcessError(1, cmd, out(entries), b"")
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], b"", b"")
        partial = ops.disk(home, run=partial_run)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["total_kb"], 9504, "the entries du could read are counted")
        self.assertEqual(partial["errors"], ["home entries: du exit 1, partial", f"projects: du stopped at its {ops.DISK_TIMEOUT_MS // 1000} s bound"])
        failed = ops.disk(os.path.join(home, "gone"), run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
        self.assertEqual(failed["status"], "failed")
        self.assertRegex(failed["error"], r"could not be listed \(ENOENT\)")
        bare = self.scratch("disk-bare-")
        os.makedirs(os.path.join(bare, "x"))
        bare_calls: list = []

        def bare_run(cmd, **kw):
            bare_calls.append(cmd[2])
            return subprocess.CompletedProcess(cmd, 0, f"7\t{os.path.join(bare, 'x')}\0".encode(), b"")
        b = ops.disk(bare, run=bare_run)
        self.assertEqual([b["status"], b["total_kb"], b["targets"], bare_calls], ["ok", 7, [], ["-xsk"]], "a home with no projects/: no tree scan, no targets")
        self.assertIn("disk", ops.OPS)
        self.assertEqual(ops.collect("disk", {"home": os.path.join(home, "gone")})["disk"]["status"], "failed")

    def test_nul_ended_records_a_newline_in_a_name_invents_nothing_outside_the_home_is_dropped_the_bound_is_said(self):
        home = self.scratch("disk-nul-")
        os.makedirs(os.path.join(home, "a\nb"))
        os.makedirs(os.path.join(home, "projects"))
        answer = f"100\t{os.path.join(home, 'a' + chr(10) + 'b')}\0999999\t/etc\0".encode()

        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, answer if "-xsk" in cmd else f"50\t{os.path.join(home, 'projects')}\0".encode(), b"")
        d = ops.disk(home, run=run)
        self.assertEqual([(e["name"], e["kb"]) for e in d["largest"]], [("a\nb", 100), ("projects", 50)], "one entry, its newline kept; /etc dropped")
        self.assertEqual(d["total_kb"], 150)

        def overflow(cmd, **kw):
            raise util.OutputOverflow(cmd, ops.DISK_MAX_BUFFER, b"", b"")
        big = ops.disk(home, run=overflow)
        self.assertTrue(all(e.endswith(f"du's output passed its {ops.DISK_MAX_BUFFER // 1048576} MiB bound") for e in big["errors"]), big["errors"])

    def test_records_outside_the_home_named_unreadable_paths_counted_the_first_named_du_in_the_c_locale(self):
        home = self.scratch("disk-carry-")
        os.makedirs(os.path.join(home, "projects"))
        os.makedirs(os.path.join(home, "x"))
        envs: list = []

        def run(cmd, **kw):
            envs.append(kw["env"].get("LC_ALL"))
            if "-xsk" in cmd:
                return subprocess.CompletedProcess(cmd, 0, (f"100\t{os.path.join(home, 'x')}\0999\t/etc\0" + f"7\t/root\0\n5\t{os.path.join(home, 'x', 'y')}\0").encode(), b"")
            raise subprocess.CalledProcessError(1, cmd, f"50\t{os.path.join(home, 'projects')}\0".encode(),
                                                (f"du: cannot read directory '{home}/projects/p/volumes/v1': Permission denied\n"
                                                 f"du: cannot read directory \"{home}/projects/it's\": Permission denied\n").encode())
        d = ops.disk(home, run=run)
        self.assertEqual(envs, ["C", "C"], "du is asked in the C locale")
        self.assertEqual(d["total_kb"], 150, "outside the home and a record after a newline count for nothing")
        self.assertEqual(d["status"], "partial")
        self.assertEqual(d["errors"], [
            f"home entries: 2 records outside {home} dropped; the first: /etc",
            "projects: du exit 1, partial",
            f"projects: 2 paths du could not read, not counted; the first: '{home}/projects/p/volumes/v1'",
        ])


def account_home(test: Base, slugs=None):
    slugs = {"claude-example-org": True} if slugs is None else slugs
    h = test.scratch("ctl-accounts-")
    d = ops.accounts_dir(h, {})
    for slug, signed_in in slugs.items():
        write(os.path.join(d, slug, ".claude.json"), json.dumps({"oauthAccount": {"emailAddress": f"{slug}@example.org", "organizationUuid": "org-1234"}}))
        if signed_in:
            write(os.path.join(d, slug, ".credentials.json"), json.dumps({"claudeAiOauth": {"accessToken": ACCESS, "refreshToken": "refresh-XYZ"}}))
    return h, d


def harness(out: str = USAGE_EVENTS, seen: list | None = None):
    def run(cmd, **kw):
        if seen is not None:
            seen.append((cmd, kw, os.path.exists(kw["cwd"])))
        return subprocess.CompletedProcess(cmd, 0, out.encode(), b"")
    return run


class Accounts(Base):
    def test_parse_usage_report_the_meters_in_the_servers_order_an_error_result_is_a_failure(self):
        r = ops.parse_usage_report(USAGE_EVENTS)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([[x["kind"], x["percent"], x["model"]] for x in r["limits"]], [["session", 11, None], ["weekly_all", 83, None], ["weekly_scoped", 86, "Opus"]])
        msg = "Failed to refresh OAuth token: another Claude Code process is refreshing it"
        self.assertEqual(ops.parse_usage_report(json.dumps([{"type": "result", "is_error": True, "result": msg}])), {"status": "failed", "error": msg})
        self.assertEqual(ops.parse_usage_report("not json")["status"], "unreadable")
        self.assertEqual(ops.parse_usage_report('[{"type": "assistant", "usage_report": {"rate_limits": {"limits": [{"kind": "s", "percent": NaN}]}}}]')["status"], "unreadable", "JSON.parse refuses NaN")
        self.assertEqual(ops.parse_usage_report("[" * 100000)["status"], "unreadable", "a document nested past the stack is a bad document")
        odd = ops.parse_usage_report(json.dumps([{"type": "assistant", "usage_report": {"rate_limits": {"limits": [{"kind": "session", "percent": "11"}, {"kind": "x", "percent": True}]}}}]))
        self.assertEqual([lim["percent"] for lim in odd["limits"]], [None, None], "a percent that is not a number is unknown, not 11 and not 1")
        self.assertEqual(ops.parse_usage_report(json.dumps([{"type": "result", "is_error": False}]))["status"], "no-report", "a success without the report is said, not read as zero usage")

    def test_read_account_the_child_runs_in_the_accounts_own_config_directory_with_no_inherited_token(self):
        h, d = account_home(self)
        seen: list = []
        saved = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-inherited-template-token"
        self.addCleanup(lambda: os.environ.__setitem__("CLAUDE_CODE_OAUTH_TOKEN", saved) if saved is not None else os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None))
        acct = os.path.join(d, "claude-example-org")
        r = ops.read_account(acct, home=h, bin="/fake/claude", now=lambda: 1790280000000, run=harness(seen=seen))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["email"], "claude-example-org@example.org")
        self.assertEqual(r["organization_uuid"], "org-1234")
        self.assertEqual(r["read_at"], "2026-09-24T20:00:00.000Z")
        self.assertEqual(seen[0][0], ["/fake/claude", "-p", "/usage", "--output-format", "json", "--no-session-persistence"])
        env = seen[0][1]["env"]
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], acct)
        for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            self.assertNotIn(k, env, f"{k} reached the child")
        self.assertTrue(seen[0][2], "the child had a working directory")
        self.assertEqual(seen[0][1]["cwd"], os.path.join(acct, "work"), "one fixed cwd inside the account: the harness records a project per cwd")
        ops.read_account(acct, home=h, bin="/fake/claude", run=harness(seen=seen))
        self.assertEqual(seen[1][1]["cwd"], seen[0][1]["cwd"], "the same one on the next read")
        self.assertNotIn(ACCESS, json.dumps(r))

    def test_read_account_never_signed_in_a_timeout_and_a_failed_run_each_say_so(self):
        h, d = account_home(self, {"not-yet": False, "slow-one": True, "broken-one": True})
        ran = [0]

        def count(cmd, **kw):
            ran[0] += 1
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        not_yet = ops.read_account(os.path.join(d, "not-yet"), home=h, run=count)
        self.assertEqual((not_yet["status"], ran[0]), ("not-signed-in", 0), "no harness is started for an account with no sign-in")

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 120)
        self.assertEqual(ops.read_account(os.path.join(d, "slow-one"), home=h, run=slow)["status"], "timeout")

        def broken(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        r = ops.read_account(os.path.join(d, "broken-one"), home=h, bin="/fake/claude", run=broken)
        self.assertEqual([r["status"], r["error"]], ["failed", "spawn /fake/claude ENOENT"])

    def test_accounts_every_observed_account_one_at_a_time_slugs_that_are_not_names_are_ignored(self):
        h, d = account_home(self, {"claude-a": True, "claude-b": True})
        os.makedirs(os.path.join(d, "Not A Slug"))
        write(os.path.join(d, "stray-file"))
        self.assertEqual(ops.account_slugs(d), ["claude-a", "claude-b"])
        live = [0, 0]

        def run(cmd, **kw):
            live[0] += 1
            live[1] = max(live[1], live[0])
            live[0] -= 1
            return subprocess.CompletedProcess(cmd, 0, USAGE_EVENTS.encode(), b"")
        r = ops.accounts(h, run=run)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([[a["slug"], a["status"]] for a in r["accounts"]], [["claude-a", "ok"], ["claude-b", "ok"]])
        self.assertEqual(ops.accounts(self.scratch("ctl-noaccounts-"))["status"], "none")

    def test_the_read_lock_one_reader_per_account_a_dead_holder_does_not_keep_it_the_state_root_is_honoured(self):
        h, d = account_home(self, {"claude-a": True})
        acct = os.path.join(d, "claude-a")
        release = ops.take_read_lock(acct, os.getpid())
        self.assertTrue(release, "the first reader takes it")
        write(os.path.join(acct, ".fabric-read.lock"), f"{os.getppid()}\n")   # a live process that is not us
        ran = [0]

        def run(cmd, **kw):
            ran[0] += 1
            return subprocess.CompletedProcess(cmd, 0, USAGE_EVENTS.encode(), b"")
        busy = ops.read_account(acct, home=h, run=run)
        self.assertEqual((busy["status"], ran[0]), ("busy", 0), "no second harness on a held account")
        write(os.path.join(acct, ".fabric-read.lock"), "999999999\n")   # a pid that cannot exist
        r = ops.read_account(acct, home=h, run=run)
        self.assertEqual((r["status"], ran[0]), ("ok", 1), "a killed reader's lock is taken over")
        self.assertFalse(os.path.exists(os.path.join(acct, ".fabric-read.lock")), "released after the read")
        self.assertEqual(ops.accounts_dir("/home/x", {"AGENT_FABRIC_STATE_DIR": "/srv/state"}), "/srv/state/accounts")
        self.assertEqual(ops.accounts_dir("/home/x", {"XDG_STATE_HOME": "/xdg"}), "/xdg/agent-fabric/accounts")

    def test_a_lock_naming_no_pid_is_busy_while_fresh_and_stale_when_old_never_a_permanent_busy(self):
        # The Node signalled pid 0 (its own process group) for an empty file and kept the account busy for good;
        # a Node daemon beside this one can be between its create and its write, so a fresh one is a holder.
        h, d = account_home(self, {"claude-a": True})
        acct = os.path.join(d, "claude-a")
        lock = os.path.join(acct, ".fabric-read.lock")
        for body in ("", "\n", "not a pid\n", "0\n", "-5\n"):
            write(lock, body)
            self.assertIsNone(ops.take_read_lock(acct), f"fresh {body!r}: its writer may be mid-write")
            old = os.stat(lock).st_mtime - 60
            os.utime(lock, (old, old))
            release = ops.take_read_lock(acct)
            self.assertTrue(release, f"old {body!r}")
            release()

    def test_a_held_lock_is_never_empty_and_a_release_removes_only_its_own(self):
        h, d = account_home(self, {"claude-a": True})
        acct = os.path.join(d, "claude-a")
        lock = os.path.join(acct, ".fabric-read.lock")
        seen: list[str] = []
        real = os.link

        def spy(src, dst, *a, **k):
            seen.append(open(src, encoding="utf-8").read())   # what the lock holds the moment it exists
            return real(src, dst, *a, **k)
        from unittest import mock
        with mock.patch.object(os, "link", spy):
            release = ops.take_read_lock(acct, 4242)
        self.assertEqual(seen, ["4242\n"])
        self.assertEqual(os.listdir(acct).count(".fabric-read.lock"), 1)
        self.assertEqual([n for n in os.listdir(acct) if n.endswith(".tmp")], [], "no temporary file is left")
        write(lock, f"{os.getppid()}\n")   # a takeover: the file is another reader's now
        release()
        self.assertTrue(os.path.exists(lock), "a release never removes a lock that names someone else")
        os.unlink(lock)
        ops.take_read_lock(acct, 7)()
        self.assertFalse(os.path.exists(lock))

    def test_the_read_lock_is_released_when_the_read_fails_before_the_harness_starts(self):
        h, d = account_home(self, {"claude-a": True})
        acct = os.path.join(d, "claude-a")
        write(os.path.join(acct, "work"), "not a directory")

        def never(cmd, **kw):
            raise AssertionError("no harness without a working directory")
        r = ops.read_account(acct, home=h, run=never)
        self.assertEqual(r["status"], "failed")
        self.assertFalse(os.path.exists(os.path.join(acct, ".fabric-read.lock")), "the lock did not outlive the failed read")

    def test_a_lock_that_cannot_be_read_is_a_loud_failure_not_a_permanent_busy(self):
        h, d = account_home(self, {"claude-a": True})
        acct = os.path.join(d, "claude-a")
        os.makedirs(os.path.join(acct, ".fabric-read.lock"))
        with self.assertRaises(OSError) as cm:
            ops.take_read_lock(acct)
        self.assertEqual(cm.exception.errno, errno.EISDIR)

        def never(cmd, **kw):
            raise AssertionError("no harness")
        r = ops.read_account(acct, home=h, run=never)
        self.assertEqual([r["status"], r["error"]], ["failed", "read lock: EISDIR"], 'the reason is named, never "another reader holds it"')
        os.makedirs(os.path.join(d, "claude-b"))
        write(os.path.join(d, "claude-b", ".credentials.json"), "{}")
        both = ops.accounts(h, run=harness())
        self.assertEqual([[a["slug"], a["status"]] for a in both["accounts"]], [["claude-a", "failed"], ["claude-b", "ok"]], "one broken lock does not blank the sibling accounts")


class Presence(Base):
    def test_a_session_is_a_claude_process_that_is_not_the_daemons_own_child(self):
        # The binding's role is checked against the catalogue (instance data, ADR-045): the operator
        # tree of this case is a copy of this checkout's, whatever AGENT_FABRIC_OPERATOR the run had.
        operator = self.scratch("presence-operator-")
        os.makedirs(os.path.join(operator, "identities", "roles"))
        shutil.copyfile(os.path.join(HERE, "identities", "roles", "catalog.json"), os.path.join(operator, "identities", "roles", "catalog.json"))
        saved = os.environ.get("AGENT_FABRIC_OPERATOR")
        os.environ["AGENT_FABRIC_OPERATOR"] = operator
        self.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_OPERATOR", saved) if saved is not None else os.environ.pop("AGENT_FABRIC_OPERATOR", None))
        proc = self.scratch("presence-proc-")
        write(os.path.join(proc, "stat"), "cpu  1 2 3\nbtime 1790000000\n")

        def stat(pid, ppid, ticks):
            # stat after the comm: state ppid pgrp session tty tpgid flags minflt cminflt majflt cmajflt utime stime cutime cstime priority nice threads itrealvalue starttime
            write(os.path.join(proc, str(pid), "stat"), f"{pid} (claude) S {ppid} 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 {ticks} 0 0")
        stat(100, 50, 1000)
        stat(200, 999, 500)
        stat(300, 60, 3000)
        binding = {"role": "web-dev", "project": "gzapp"}
        who = {"agent": "web-dev-01", "host": "h", "role": "web-dev", "binding": "/nonexistent"}
        not_held = lambda: {"held": False}  # noqa: E731

        def pgrep(out="", rc=0):
            def run(cmd, **kw):
                if rc:
                    raise subprocess.CalledProcessError(rc, cmd, out, "")
                return subprocess.CompletedProcess(cmd, 0, out, "")
            return run
        r = ops.presence(proc=proc, self_pid=999, run=pgrep("100\n200\n300\n"), who=who, binding=binding, hold_status=not_held)
        self.assertEqual(r, {"status": "ok", "online": True, "sessions": 2, "since": ops.util.iso_ms((1790000000 + 10) * 1000), "role": "web-dev", "project": "gzapp", "planning": False},
                         "the daemon's child (200) is not a session; the earliest start is the since")
        unbound = ops.presence(proc=proc, self_pid=999, run=pgrep("100\n"), who={"agent": "web-dev-02", "host": "h", "role": None, "binding": "/nonexistent"}, binding={}, hold_status=not_held)
        self.assertEqual(unbound["role"], "web-dev", "no binding role: the slug the login carries")
        none = ops.presence(proc=proc, self_pid=999, run=pgrep("", 1), who=who, binding=binding)
        self.assertEqual([none["online"], none["sessions"], none["since"]], [False, 0, None], "pgrep finding nothing is offline")

        def enoent(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        self.assertEqual(ops.presence(proc=proc, self_pid=999, run=enoent, who=who, binding=binding)["status"], "failed", 'a pgrep that cannot run is not "offline"')
        self.assertEqual(ops.presence(proc=proc, self_pid=999, run=pgrep("", 2), who=who, binding=binding)["status"], "failed")
        self.assertIs(ops.presence(proc=proc, self_pid=999, run=pgrep("100\n"), who=who, binding=binding, hold_status=lambda: {"held": True})["planning"], True, "a held inbox is planning")
        self.assertIs(ops.presence(proc=proc, self_pid=999, run=pgrep("", 1), who=who, binding=binding, hold_status=lambda: {"held": True})["planning"], False,
                      "no session is never planning, whatever a stale marker says")

        def no_hold():
            raise OSError("no hold dir")
        self.assertIs(ops.presence(proc=proc, self_pid=999, run=pgrep("100\n"), who=who, binding=binding, hold_status=no_hold)["planning"], False, "an unreadable hold is not planning")


if __name__ == "__main__":
    unittest.main()
