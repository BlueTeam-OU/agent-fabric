#!/usr/bin/env python3
"""The modules that wrote under agents/<login>/ themselves now write through runtime/identity.py (agent-fabric ADR-003 rule 1,
j577). Each case pins one converted write and fails on the code it replaced: a file made under umask 022 is 0600 where the
old open() left 0644, a state directory is the one identity.state_root() says where a private copy of the resolution said
another, a log goes through identity.append_line (one flock'd write; rotation under its own lock), a lock file takes no
content. The writers' own contracts (atomic_write, append_line) are tests/test_identity.py's."""
from __future__ import annotations

import json
import multiprocessing
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERE, "tools", "fabric")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import gh_ledger  # noqa: E402
import harvest_memory  # noqa: E402
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
import launch_locale  # noqa: E402
import launch_provider_record  # noqa: E402
import ledger  # noqa: E402
import query  # noqa: E402
from fabric_launcher import gateway, gateway_usage  # noqa: E402
from gzcoord import gzmsg  # noqa: E402
from memory_mcp import calls  # noqa: E402
from provisioning import persist_accounts  # noqa: E402
import memory_flagrun  # noqa: E402

LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def mode(path: str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _append_many(args: tuple[str, int, int]) -> None:
    path, who, n = args
    for i in range(n):
        ledger.append(path, {"who": who, "i": i, "pad": "x" * 6000})


def _gh_record(args: tuple[str, int]) -> None:
    os.environ["AGENT_FABRIC_STATE_DIR"] = args[0]
    gh_ledger.MAX_BYTES = 600
    gh_ledger.record(["api", "x"], f"w{args[1]}", 200, 0.1)


class Private(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="identity-writers.")
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state")
        env = mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": self.state})
        env.start()
        self.addCleanup(env.stop)
        old = os.umask(0o022)   # the usual one: a file made without a mode of its own is 0644
        self.addCleanup(os.umask, old)
        self.agent = os.path.join(self.state, "agents", LOGIN)
        os.makedirs(self.agent)

    def test_the_launch_provider_record_is_0600_and_keep_existing_still_refuses(self) -> None:
        self.assertTrue(launch_provider_record.write(self.agent, "openai"))
        path = os.path.join(self.agent, launch_provider_record.RECORD)
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(json.loads(read(path))["provider"], "openai")
        self.assertFalse(launch_provider_record.write(self.agent, "anthropic", keep_existing=True))
        self.assertEqual(json.loads(read(path))["provider"], "openai", "a kept record is not overwritten")
        self.assertEqual([n for n in os.listdir(self.agent) if n.startswith(".tmp-")], [], "no temporary left behind")

    def test_the_gateway_record_and_its_usage_file_are_0600(self) -> None:
        gw = gateway.Gateway(proc=mock.Mock(pid=7), listener="l", plan_digest="d", version="v", runtime_contract=1, key="k",
                             control=mock.Mock(), started_at="t")
        gateway.record_state(self.agent, gw)
        self.assertEqual(mode(os.path.join(self.agent, "gateway.json")), 0o600)
        self.assertIsNone(gateway_usage.write(self.agent, {"version": 1}))
        self.assertEqual(mode(os.path.join(self.agent, gateway_usage.FILE)), 0o600)

    def test_the_launch_record_is_written_and_read_by_identity_s_state_directory(self) -> None:
        launch_locale.record(self.agent, "ru")
        self.assertEqual(mode(os.path.join(self.agent, launch_locale.FILE)), 0o600)
        self.assertEqual(launch_locale.read(LOGIN), "ru")
        moved = os.path.join(self.tmp.name, "moved")
        os.makedirs(os.path.join(moved, "agents", "someone"))
        launch_locale.record(os.path.join(moved, "agents", "someone"), "ka")
        with mock.patch.object(launch_locale.identity, "state_root", lambda: moved):
            self.assertEqual(launch_locale.read("someone"), "ka", "the state directory is identity's, not a copy of its rule")

    def test_the_queries_and_whoami_find_the_binding_where_identity_says(self) -> None:
        moved = os.path.join(self.tmp.name, "moved")
        wc = os.path.join(self.tmp.name, "wc")
        os.makedirs(os.path.join(wc, ".agent-fabric", "memory"))
        os.makedirs(os.path.join(moved, "agents", LOGIN))
        with open(os.path.join(moved, "agents", LOGIN, "binding.json"), "w") as fh:
            json.dump({"working_copy": wc, "role": "python-dev"}, fh)
        with mock.patch.object(query.identity, "state_root", lambda: moved), \
                mock.patch.dict(os.environ, {"AGENT_FABRIC_WORKING_COPY": "", "AGENT_FABRIC_WORKING_COPIES": ""}):
            self.assertIn(os.path.join(wc, ".agent-fabric", "memory"), query.project_roots(self.tmp.name, os.path.join(self.tmp.name, "m")))
        # identity.py reads an empty override as none; the Node's `??` copy this replaced read it as a base of "".
        xdg = os.path.join(self.tmp.name, "xdg")
        os.makedirs(os.path.join(xdg, "agent-fabric", "agents", LOGIN))
        with open(os.path.join(xdg, "agent-fabric", "agents", LOGIN, "binding.json"), "w") as fh:
            json.dump({"role": "python-dev"}, fh)
        real = gzmsg._identity_module
        first = []

        def answers_once_wrongly(root: str):
            if not first:   # the first load is whoami's own; the fallback's load, beside gzmsg, is the second
                first.append(root)
                raise RuntimeError("identity cannot answer")
            return real(root)
        with mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": "", "XDG_STATE_HOME": xdg}), \
                mock.patch.object(gzmsg, "_identity_module", answers_once_wrongly):
            me = gzmsg.whoami()
        self.assertTrue(me.get("fallback"))
        self.assertEqual(me["binding"], os.path.join(xdg, "agent-fabric", "agents", LOGIN, "binding.json"))
        self.assertEqual(me["role"], "python-dev")

    def test_the_ledger_path_is_identity_s_and_parallel_appends_stay_whole(self) -> None:
        self.assertEqual(ledger.path(), os.path.join(self.agent, "ledger.jsonl"))
        path = ledger.path()
        with multiprocessing.Pool(4) as pool:
            pool.map(_append_many, [(path, w, 10) for w in range(4)])
        rows = [json.loads(line) for line in read(path).splitlines()]
        self.assertEqual(len(rows), 40)
        self.assertEqual(mode(path), 0o600)
        with mock.patch.object(ledger.identity, "append_line") as spy:
            ledger.append(path, {"a": 1})
        self.assertEqual(spy.call_args.kwargs.get("wait"), ledger.LOCK_WAIT_S, "the bounded wait is kept")

    def test_the_gh_ledger_rotates_once_under_racing_writers(self) -> None:
        path = os.path.join(self.agent, gh_ledger.LEDGER)
        with open(path, "w") as fh:
            fh.write("x" * 700)
        with multiprocessing.Pool(3) as pool:
            pool.map(_gh_record, [(self.state, n) for n in range(3)])
        self.assertEqual(read(path + ".1"), "x" * 700, "the generation kept is the full one, not overwritten by a later rotation")
        self.assertEqual(len(read(path).splitlines()), 3)
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(mode(path + ".lock"), 0o600)
        with mock.patch.object(gh_ledger.identity, "append_line") as spy:
            gh_ledger.record(["api", "x"], "t", 200, 0.1)
        self.assertEqual(spy.call_args.kwargs.get("max_bytes"), gh_ledger.MAX_BYTES, "rotation is identity's, not a private _rotate")

    def test_the_memory_call_log_is_one_locked_private_line_per_call(self) -> None:
        sub = os.path.join(self.tmp.name, "fresh-state")
        self.assertIsNone(calls.append_line(sub, calls.LOG, {"tool": "find"}))
        self.assertEqual(mode(os.path.join(sub, calls.LOG)), 0o600)
        self.assertEqual(mode(sub), 0o700)
        with mock.patch.object(calls.identity, "append_line") as spy:
            calls.append_line(sub, calls.LOG, {"tool": "read"})
        self.assertEqual(spy.call_args.args[0], os.path.join(sub, calls.LOG))

    def test_the_snapshot_lock_is_0600_and_takes_no_truncation(self) -> None:
        snap = os.path.join(self.tmp.name, "snap")
        os.makedirs(snap)
        lock = os.path.join(snap, ".lock")
        with open(lock, "w") as fh:
            fh.write("kept")
        held = persist_accounts._lock(snap, 0)
        self.addCleanup(held.close)
        self.assertEqual(read(lock), "kept", "a lock file is never truncated")
        os.unlink(lock)
        persist_accounts._lock(snap, 0).close()
        self.assertEqual(mode(lock), 0o600)

    def test_the_flag_request_is_staged_outside_the_state_directory(self) -> None:
        seen = os.path.join(self.tmp.name, "seen")
        script = os.path.join(self.tmp.name, "send.py")
        with open(script, "w") as fh:
            fh.write(f"import sys\nopen({seen!r}, 'w').write(sys.argv[1])\n")
        rc, _ = memory_flagrun.send_request([sys.executable, script], "text")
        self.assertEqual(rc, 0)
        staged = read(seen)
        self.assertTrue(os.path.basename(staged) == "request.txt" and not os.path.realpath(staged).startswith(os.path.realpath(self.state) + os.sep), staged)

    def test_the_drain_bundle_is_replaced_whole(self) -> None:
        drain = os.path.join(self.tmp.name, "drain")
        os.makedirs(os.path.join(drain, "claims"))
        for name in ("harvest-report.json", "references.json"):
            with open(os.path.join(drain, name), "w") as fh:
                fh.write("{}\n")
        report = {"agent": "a", "host": "h", "role": "r", "project": "p", "working_copy": "w", "since_watermark": 0,
                  "next_watermark": 1, "claims": 0, "oldest_drainable_ms": None}
        target = os.path.join(self.agent, "drain", "bundle.tar")
        os.makedirs(os.path.dirname(target))
        with mock.patch.object(harvest_memory.identity, "atomic_write", wraps=harvest_memory.identity.atomic_write) as spy, \
                mock.patch("sys.stderr"):
            self.assertEqual(harvest_memory.write_bundle(drain, target, report), 0)
        self.assertEqual(spy.call_args.args[0], target)
        import tarfile
        with tarfile.open(target) as tar:
            self.assertEqual(tar.getnames(), ["manifest.json", "harvest-report.json", "references.json"])


if __name__ == "__main__":
    unittest.main()
