#!/usr/bin/env python3
"""The two-account live check (tests/live_interweave_two_accounts.py, not part of the suite) serves the config
`render-config` prints for this account over the whole verified roster, not one narrowed to the pair under test
(#598 P3, F4/F5): the live check must run the config the carrier unit gets."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import sys
import types
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord import paths  # noqa: E402
from gzcoord.carrier import main as M  # noqa: E402
from gzcoord.carrier import roster as R  # noqa: E402

_spec = importlib.util.spec_from_file_location("live_pair_under_test", os.path.join(ROOT, "tests", "live_interweave_two_accounts.py"))
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


def row(login: str, port: int, **more) -> dict:
    # render_config reads no signature: the rows here are already judged
    return {"agent_id": f"id-{login}", "login": login, "peer_id": f"peer-{login}", "port": port, **more}


HOSTS = {"h2": {"interweave_address": "192.0.2.7"}}


def roster(rows: list[dict], hosts: dict | None = None) -> R.Roster:
    return R.Roster("gzcoord", "gzcoord", (47100, 47199), tuple(rows), hosts or {})


class WholeRosterRender(unittest.TestCase):
    A, B, G = row("alpha", 47101), row("beta", 47102), row("gamma", 47103)
    ME = types.SimpleNamespace(agent_id="id-alpha", address="h1/alpha")

    def seams(self, rows, hosts=None, me=None):
        return (unittest.mock.patch.object(M, "verified_roster", return_value=(roster(rows, hosts), list(rows))),
                unittest.mock.patch.object(M, "make_me", return_value=me or self.ME))

    def cmd_render_text(self, rows, hosts=None) -> str:
        a, b = self.seams(rows, hosts)
        out = io.StringIO()
        with a, b, contextlib.redirect_stdout(out):
            self.assertEqual(M.cmd_render(None), 0)
        return out.getvalue()

    def live_render_text(self, rows, hosts=None) -> str:
        a, b = self.seams(rows, hosts)
        with a, b:
            return live.render_text()

    def test_render_text_is_what_render_config_prints_for_the_whole_roster(self):
        rows = [self.A, self.B, self.G, row("delta", 47104, host="h2")]
        self.assertEqual(self.live_render_text(rows, HOSTS), self.cmd_render_text(rows, HOSTS))
        got = self.live_render_text(rows, HOSTS)
        for peer in ("peer-beta", "peer-gamma", "peer-delta"):
            self.assertIn(peer, got)
        self.assertIn("/ip4/192.0.2.7/tcp/47104", got)

    def test_positive_control_a_two_row_roster_renders_without_the_third(self):
        self.assertNotIn("peer-gamma", self.live_render_text([self.A, self.B]))

    def test_own_host_refusal_comes_through_render_text(self):
        rows = [row("alpha", 47101, host="h2"), self.B]
        a, b = self.seams(rows, HOSTS)
        with a, b, self.assertRaises(live.RenderRefused) as ctx:
            live.render_text()
        self.assertIn("the row and the address must agree", str(ctx.exception))

    def test_judged_roster_drops_no_row(self):
        rows = [self.A, self.B, self.G]
        a, b = self.seams(rows)
        with a, b:
            r, good = live.judged_roster()
        self.assertEqual([x["login"] for x in r.rows], ["alpha", "beta", "gamma"])
        self.assertEqual([x["login"] for x in good], ["alpha", "beta", "gamma"])

    def serve(self, rows, existing: str | None = None):
        """phase_serve with the processes faked; returns (rc, config text or None)."""
        a, b = self.seams(rows)
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.yaml")
            if existing is not None:
                with open(cfg, "w", encoding="utf-8") as fh:
                    fh.write(existing)
            with a, b, unittest.mock.patch.object(live, "LOGIN", "alpha"), unittest.mock.patch.object(live, "PEER", "beta"), \
                    unittest.mock.patch.object(live, "WORK", os.path.join(d, "work")), \
                    unittest.mock.patch.object(live, "config_path", return_value=cfg), \
                    unittest.mock.patch.object(live, "phase_check", return_value=0), \
                    unittest.mock.patch.object(live, "spawn", return_value=1), unittest.mock.patch.object(live, "until", return_value=True), \
                    unittest.mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                rc = live.phase_serve()
            if not os.path.exists(cfg):
                return rc, None
            with open(cfg, encoding="utf-8") as fh:
                return rc, fh.read()

    def test_serve_writes_the_whole_roster_config(self):
        rows = [self.A, self.B, self.G]
        rc, text = self.serve(rows)
        self.assertEqual(rc, 0)
        self.assertEqual(text, self.cmd_render_text(rows))
        self.assertIn("peer-gamma", text)

    def test_serve_compares_an_existing_config_against_that_same_text(self):
        rows = [self.A, self.B, self.G]
        rc, text = self.serve(rows, existing=self.cmd_render_text(rows))
        self.assertEqual(rc, 0)
        # the pair-only render is a different file: it is refused, not accepted
        rc, text = self.serve(rows, existing=self.cmd_render_text([self.A, self.B]))
        self.assertEqual(rc, 2)
        self.assertEqual(text, self.cmd_render_text([self.A, self.B]))


if __name__ == "__main__":
    unittest.main()
