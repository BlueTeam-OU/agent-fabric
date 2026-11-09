#!/usr/bin/env python3
"""runtime/identity.py's typed context (j212): resolve_context answers a frozen AgentContext built from AgentIdentity,
ProjectContext and BindingRecord, and every caller that took the flat dict still reads it.

Each case names the mutation it kills:

  context_is_typed_and_frozen   <- resolve_context returning a dict again, or any of the four dataclasses unfrozen
  flat_view_is_the_old_dict     <- as_dict dropping or adding a key (`--json` and the launcher parse it), the Mapping view
                                   disagreeing with it
  binding_record_is_the_file    <- BindingRecord filled from the resolved project instead of the binding's, `present` always
                                   true, an empty or non-string value not read as None
  refused_binding_still_raises  <- resolve_context catching what read_binding refuses
  loaded_by_path_without_registering <- the _frozen stand-in dropped: tools load identity.py with spec_from_file_location
  json_matches_the_context      <- `identity.py --json` printing something other than as_dict()
  binding_record_skips_the_copy <- binding_record resolving cwd's working copy (a bad marker or registry there costs the
                                   binding, #511 F15), or reading fields resolve_context's .binding does not
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
IDENTITY = os.path.join(HERE, "runtime", "identity.py")
FLAT_KEYS = {"agent", "host", "address", "role", "project", "project_source", "working_copy", "working_copy_id",
             "remote", "session", "cwd", "fabric_root", "state_dir"}


def load_by_path():
    """As tools/fabric/gzcoord/gzmsg.py and the launcher do: the module is never put in sys.modules."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_identity_under_test", IDENTITY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "fabric_identity_under_test" not in sys.modules
    return module


class Context(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="identity-context-")
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state")
        self.cwd = os.path.join(self.tmp.name, "nowhere")   # outside any repository: no working-copy project
        os.makedirs(self.cwd)
        self.env = mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": self.state, "CLAUDE_SESSION_ID": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity = load_by_path()

    def bind(self, record) -> str:
        path = self.identity.binding_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(record if isinstance(record, str) else json.dumps(record))
        return path

    def test_context_is_typed_and_frozen(self) -> None:
        ctx = self.identity.resolve_context(cwd=self.cwd)
        self.assertIsInstance(ctx, self.identity.AgentContext)
        for value in (ctx, ctx.identity, ctx.project, ctx.binding):
            self.assertTrue(dataclasses.is_dataclass(value))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(value, dataclasses.fields(value)[0].name, "x")
        self.assertEqual((ctx.identity.agent, ctx.identity.address), (LOGIN, f"{ctx.identity.host}/{LOGIN}"))

    def test_the_flat_view_is_the_dict_callers_took(self) -> None:
        self.bind({"role": "python-dev", "project": "agent-fabric"})
        ctx = self.identity.resolve_context(cwd=self.cwd, session="s-1")
        flat = ctx.as_dict()
        self.assertEqual(set(flat), FLAT_KEYS)
        self.assertEqual((flat["role"], flat["project"], flat["project_source"], flat["session"]),
                         ("python-dev", "agent-fabric", "binding", "s-1"))
        self.assertEqual(dict(ctx), flat)
        self.assertEqual((ctx["agent"], ctx.get("role"), ctx.get("nope", 7), len(ctx)), (LOGIN, "python-dev", 7, len(FLAT_KEYS)))
        self.assertNotIn("binding", ctx, "what the dict never held stays on .binding")

    def test_the_binding_record_is_the_file_and_not_the_resolved_project(self) -> None:
        wc = os.path.join(self.tmp.name, "clone")
        self.bind({"role": "python-dev", "project": "bound-project", "working_copy": wc})
        bound = self.identity.resolve_context(cwd=self.cwd).binding
        self.assertEqual((bound.role, bound.project, bound.working_copy, bound.present), ("python-dev", "bound-project", wc, True))
        self.assertEqual(bound.file, self.identity.binding_path())
        self.bind({"role": "python-dev", "updated_at": "2026-01-02T03:04:05Z"})
        self.assertEqual(self.identity.resolve_context(cwd=self.cwd).binding.updated_at, "2026-01-02T03:04:05Z")
        self.assertEqual(self.identity.binding_record().updated_at, "2026-01-02T03:04:05Z")
        self.bind({"role": "", "project": 3, "working_copy": None})
        empty = self.identity.resolve_context(cwd=self.cwd).binding
        self.assertEqual((empty.role, empty.project, empty.working_copy, empty.present), (None, None, None, True),
                         "an empty or non-string value is no value; a file that is there is present")
        self.assertIsNone(empty.updated_at)
        os.remove(self.identity.binding_path())
        gone = self.identity.resolve_context(cwd=self.cwd).binding
        self.assertEqual((gone.role, gone.present), (None, False))

    def test_a_binding_identity_refuses_still_raises(self) -> None:
        for text in ("{not json", "[]", json.dumps({"agent": "someone-else"}), json.dumps({"host": "not-this-host"})):
            self.bind(text)
            with self.assertRaises(SystemExit, msg=text):
                self.identity.resolve_context(cwd=self.cwd)

    def test_a_rebind_counts_another_hosts_binding_as_none(self) -> None:
        self.bind({"host": "not-this-host", "role": "python-dev"})
        bound = self.identity.resolve_context(cwd=self.cwd, rebind=True).binding
        self.assertEqual((bound.role, bound.present), (None, True))

    def test_json_prints_the_flat_view(self) -> None:
        self.bind({"role": "python-dev"})
        r = subprocess.run([sys.executable, IDENTITY, "--json", "--cwd", self.cwd], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "AGENT_FABRIC_STATE_DIR": self.state})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(json.loads(r.stdout)), FLAT_KEYS)
        self.assertEqual(json.loads(r.stdout)["role"], "python-dev")

    def test_whoami_carries_what_the_binding_records_for_the_callers_that_read_the_file(self) -> None:
        sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
        from gzcoord import gzmsg
        wc = os.path.join(self.tmp.name, "clone")
        path = self.bind({"role": "python-dev", "project": "bound-project", "working_copy": wc})
        with mock.patch.dict(os.environ, {"AGENT_FABRIC_ROOT": HERE}):
            me = gzmsg.whoami()
        self.assertFalse(me.get("fallback"))
        self.assertEqual((me["binding"], me["bound_project"], me["bound_working_copy"]), (path, "bound-project", wc))

    def test_open_log_fd_is_an_append_descriptor_at_0600(self) -> None:
        path = os.path.join(self.tmp.name, "gateway.log")
        self.addCleanup(os.umask, os.umask(0o022))
        fd = self.identity.open_log_fd(path)
        try:
            os.write(fd, b"a\n")
        finally:
            os.close(fd)
        fd = self.identity.open_log_fd(path)
        try:
            os.write(fd, b"b\n")
        finally:
            os.close(fd)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"a\nb\n")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_binding_record_skips_the_copy(self) -> None:
        self.bind({"role": "python-dev", "project": "p", "working_copy": "/w"})
        self.assertEqual(self.identity.binding_record(), self.identity.resolve_context(cwd=self.cwd).binding)
        # A checkout whose marker names a project the registry lacks: resolve_context refuses, the binding alone does not.
        bad = os.path.join(self.tmp.name, "bad")
        os.makedirs(bad)
        subprocess.run(["git", "-C", bad, "init", "-q"], check=True)
        with open(os.path.join(bad, ".agent-fabric-project"), "w", encoding="utf-8") as fh:
            fh.write("not-registered\n")
        with self.assertRaises(SystemExit):
            self.identity.resolve_context(cwd=bad)
        old = os.getcwd()
        os.chdir(bad)
        self.addCleanup(os.chdir, old)
        rec = self.identity.binding_record()
        self.assertEqual((rec.role, rec.project, rec.working_copy, rec.present), ("python-dev", "p", "/w", True))


if __name__ == "__main__":
    unittest.main(verbosity=1)
