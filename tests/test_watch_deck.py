#!/usr/bin/env python3
"""tools/fabric/watch.py's identity header and jobs block: the job order, what draw() lets through to a terminal, the
avatar slot in each mode, and the real `--once` on a pseudo-terminal in blocks mode and under TERM_PROGRAM=herdr.

Each case fails when its guard is removed: jobs sort by priority (high, normal, low), within it active, blocked, queued,
delivered, then by the number in the id, a blocked job names what it waits on; a job title or a persona name holding an
escape sequence is drawn as `?`, while a Row's prefix — the avatar's own generated colour sequences — is kept; the avatar
is half blocks or one kitty transmission by mode, None without a mode, a placeholder the width of the picture while it
loads, a narrow terminal has none, and a refused file has none; the piped --once has no escape at all."""
from __future__ import annotations

import base64
import io
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import watch  # noqa: E402
import test_avatar  # noqa: E402

ESC = "\x1b"
AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"


def job(ident: str, state: str, priority: str = "normal", title: str = "t", blocked_on: str | None = None) -> dict:
    out = {"id": ident, "state": state, "priority": priority, "title": title}
    if blocked_on is not None:
        out["blocked_on"] = blocked_on
    return out


def put(path: str, data: str | bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    test_avatar.write(path, data)


class FakeDisk:
    def poll(self): pass
    def value(self): return 2048, 5.0, None
    def wait(self, timeout=0.0): pass


class Jobs(unittest.TestCase):
    def ids(self, jobs: list[dict]) -> list[str]:
        return [line.split()[0] for line in watch.jobs_block(json.dumps(jobs)) if not line.startswith("      ")]

    def test_priority_first_then_state_then_the_number_in_the_id(self):
        jobs = [job("j9", "delivered", "high"), job("j10", "queued", "normal"), job("j2", "active", "low"), job("j3", "blocked", "normal"),
                job("j11", "active", "normal"), job("j4", "queued", "high"), job("j5", "active", "high"), job("j6", "blocked", "high"),
                job("j12", "active", "normal")]
        self.assertEqual(self.ids(jobs), ["j5", "j6", "j4", "j9", "j11", "j12", "j3", "j10", "j2"])

    def test_the_id_is_compared_as_a_number_not_as_text(self):
        self.assertEqual(self.ids([job("j100", "active"), job("j20", "active"), job("j3", "active")]), ["j3", "j20", "j100"])

    def test_an_unknown_priority_or_state_sorts_last_and_a_missing_one_is_said(self):
        jobs = [job("j1", "weird", "normal"), job("j2", "active", "urgent"), job("j3", "delivered", "normal"), {"id": "j4"}]
        self.assertEqual(self.ids(jobs), ["j3", "j1", "j2", "j4"])
        self.assertIn("?", watch.jobs_block(json.dumps([{"id": "j4"}]))[0])

    def test_a_blocked_job_says_what_it_waits_on_and_others_do_not(self):
        lines = watch.jobs_block(json.dumps([job("j1", "blocked", blocked_on="settings-put (#236)"), job("j2", "blocked"), job("j3", "active", blocked_on="x")]))
        self.assertEqual([line for line in lines if "waits on" in line], ["      waits on: settings-put (#236)", "      waits on: (not said)"])

    def test_no_jobs_a_failure_and_a_wrong_shape_are_said_not_hidden(self):
        self.assertEqual(watch.jobs_block("[]"), ["no open jobs"])
        self.assertEqual(watch.jobs_block("fabric-jobs: no job file\nsecond"), ["fabric-jobs: no job file", "second"])
        self.assertEqual(watch.jobs_block('{"a": 1}'), ["(fabric-jobs: its answer is not a list of jobs)"])
        self.assertEqual(watch.jobs_block(json.dumps([1, "x", None])), ["no open jobs"])


class Draw(unittest.TestCase):
    def drawn(self, lines) -> str:
        out = io.StringIO()
        watch.draw(lines, clear=False, out=out)
        return out.getvalue()

    def test_a_title_with_an_escape_is_neutralised_and_the_avatars_prefix_is_kept(self):
        generated = f"{ESC}[38;2;1;2;3;48;2;4;5;6m▀{ESC}[0m"
        body = self.drawn([watch.Row(generated, f"AI {ESC}[2Jx{ESC}]0;title\x07"), *watch.jobs_block(json.dumps([job("j1", "active", title=f"a{ESC}[31mred{ESC}[0m\x9b2J")]))])
        lines = body.split("\n")
        self.assertTrue(lines[0].startswith(generated), "the generated sequences are drawn")
        self.assertNotIn(ESC, lines[0][len(generated):], "and nothing after them carries one")
        self.assertNotIn(ESC, lines[1])
        self.assertNotIn("\x9b", body)
        self.assertNotIn("\x07", body)
        self.assertEqual(body.count(ESC), generated.count(ESC))

    def test_the_text_of_a_plain_line_cannot_carry_an_escape_either(self):
        self.assertNotIn(ESC, self.drawn(f"{ESC}[2Jhello\nworld"))

    def test_a_row_text_that_is_a_prefix_look_alike_is_not_kept(self):
        self.assertNotIn(ESC, self.drawn([watch.Row("", f"{ESC}[38;2;1;2;3m▀")]))


class Slot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-slot-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.png = test_avatar.png(40, 40, test_avatar.picture(40, 40, 3))
        self.path = os.path.join(self.tmp, "a.png")
        put(self.path, self.png)

    def slot(self, mode):
        s = watch.AvatarSlot(mode, os.path.join(self.tmp, "cache"))
        s.set_path(self.path)
        s.wait()
        return s

    def test_blocks_mode_is_ten_rows_of_half_blocks_and_a_gap(self):
        rows = self.slot("blocks").prefixes()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r.startswith(f"{ESC}[38;2;") and r.endswith(f"{ESC}[0m  ") for r in rows))

    def test_kitty_mode_transmits_the_file_as_it_is_once_and_moves_to_the_text_column_on_every_row(self):
        rows = self.slot("kitty").prefixes()
        self.assertEqual(len(rows), 10)
        self.assertTrue(rows[0].endswith(watch.GO_TO_TEXT) and rows[0].startswith(f"{ESC}_G"))
        self.assertEqual(rows[1:], [watch.GO_TO_TEXT] * 9)
        payload = "".join(re.findall(r";([A-Za-z0-9+/=]*)" + re.escape(f"{ESC}\\"), rows[0]))
        self.assertEqual(base64.b64decode(payload), self.png)

    def test_no_mode_is_no_avatar_and_no_file_is_none(self):
        self.assertIsNone(self.slot(None).prefixes())
        s = watch.AvatarSlot("blocks", self.tmp)
        s.set_path(None)
        self.assertIsNone(s.prefixes())

    def test_a_refused_file_has_none_and_does_not_raise(self):
        put(self.path, test_avatar.png(2, 2, [b"\0" * 2] * 2, colour=0))
        self.assertIsNone(self.slot("blocks").prefixes())
        put(self.path, b"not a png")
        self.assertIsNone(self.slot("kitty").prefixes())

    def test_while_it_loads_the_room_it_will_take_is_blank(self):
        s = watch.AvatarSlot("blocks", self.tmp)
        s.path = self.path                                           # chosen, thread not started: loading
        self.assertEqual(s.prefixes(), [" " * watch.TEXT_COLUMN] * 10)

    def test_a_narrow_terminal_gets_no_avatar_and_a_wide_one_does(self):
        deck = watch.Deck({"HOME": self.tmp, "AGENT_FABRIC_SECRET_STORE": os.path.join(self.tmp, "store")}, os.path.join(self.tmp, "claims.json"),
                          "blocks", proc=os.path.join(self.tmp, "proc"), uid=0, disk=FakeDisk(), version_of=lambda h: "1")
        put(os.path.join(self.tmp, "store", "settings", "avatar.png"), self.png)
        put(os.path.join(self.tmp, "store", ".agent-id"), AGENT)
        status = json.dumps({"agent": "pd-x", "role": "python-dev"})
        deck.identity(status)                                         # starts the decode
        deck.slot.wait()
        narrow, _ = deck.identity(status, columns=watch.AVATAR_MIN_COLUMNS - 1)
        wide, _ = deck.identity(status, columns=watch.AVATAR_MIN_COLUMNS)
        self.assertTrue(all(isinstance(r, str) for r in narrow))
        self.assertTrue(all(isinstance(r, watch.Row) for r in wide))
        self.assertEqual(len(wide), watch.HEADER_ROWS)

    def test_a_failed_fabric_status_shows_what_it_said_in_place_of_the_login_lines(self):
        deck = watch.Deck({"HOME": self.tmp}, os.path.join(self.tmp, "claims.json"), None, proc=os.path.join(self.tmp, "proc"), uid=0,
                          disk=FakeDisk(), version_of=lambda h: "1")
        rows, name = deck.identity("fabric-status: no binding\nrun fabric-role")
        self.assertEqual((rows[1], rows[2]), ("fabric-status: no binding", "run fabric-role"))
        self.assertEqual(name, "(login unknown)")


class Terminals(unittest.TestCase):
    def test_the_shipped_list_names_the_pane_host_and_a_broken_one_lists_none(self):
        self.assertEqual(watch.kitty_terminals(HERE), ["herdr"])
        tmp = tempfile.mkdtemp(prefix="watch-term-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertEqual(watch.kitty_terminals(tmp), [], "no file")
        for text in ("{nope", "[]", '{"kitty_terminal_programs": "herdr"}', '{"kitty_terminal_programs": [1, "", null]}'):
            with self.subTest(text):
                put(os.path.join(tmp, "runtime", "control", "watch-graphics.json"), text)
                self.assertEqual(watch.kitty_terminals(tmp), [])


class Once(unittest.TestCase):
    """The real command on a pseudo-terminal, with fake fabric-status and fabric-jobs in a scratch root."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-once-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "root")
        for name, body in (("fabric-status", "echo '{\"agent\":\"pd-x\",\"role\":\"python-dev\"}'"),
                           ("fabric-jobs", "echo '[{\"id\":\"j1\",\"state\":\"active\",\"priority\":\"high\",\"title\":\"a\\u001b[2Jb\"}]'"),
                           ("fabric-pr", "echo none")):
            path = os.path.join(self.root, "bin", name)
            put(path, "#!/bin/sh\n" + body + "\n")
            os.chmod(path, 0o755)
        put(os.path.join(self.tmp, "home", ".local", "share", "agent-fabric", "secrets", "settings", "avatar.png"),
                          test_avatar.png(40, 40, test_avatar.picture(40, 40, 3)))
        os.makedirs(os.path.join(self.tmp, "home", "projects"))
        os.makedirs(os.path.join(self.root, "runtime", "control"))
        shutil.copy(os.path.join(HERE, "runtime", "control", "watch-graphics.json"), os.path.join(self.root, "runtime", "control"))

    def run_once(self, term_program: str | None, tty: bool) -> str:
        env = {"HOME": os.path.join(self.tmp, "home"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "AGENT_FABRIC_ROOT": self.root,
               "TMPDIR": self.tmp}
        if term_program:
            env["TERM_PROGRAM"] = term_program
        argv = [sys.executable, os.path.join(HERE, "tools", "fabric", "watch.py"), "--once"]
        if not tty:
            return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60, check=True, stdin=subprocess.DEVNULL).stdout
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave, close_fds=True)
        finally:
            os.close(slave)
        chunks = []
        try:
            while True:
                if not select.select([master], [], [], 60)[0]:
                    proc.kill()
                    self.fail("no output")
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
        finally:
            os.close(master)
            proc.wait(60)
        self.assertEqual(proc.returncode, 0)
        return b"".join(chunks).decode("utf-8", "replace")

    def test_piped_has_all_three_blocks_and_no_escape(self):
        out = self.run_once("herdr", tty=False)
        self.assertNotIn(ESC, out)
        self.assertLess(out.index("── pd-x ("), out.index("── jobs ──"))
        self.assertLess(out.index("── jobs ──"), out.index("── pull requests (read "))
        self.assertIn("pd-x · python-dev", out)
        self.assertIn("a?[2Jb", out)

    def test_on_a_terminal_blocks_mode_draws_the_avatar_and_neutralises_the_title(self):
        out = self.run_once(None, tty=True)
        self.assertIn(f"{ESC}[38;2;", out)
        self.assertIn("▀", out)
        self.assertNotIn(f"{ESC}_G", out)
        self.assertNotIn(f"a{ESC}", out)
        self.assertIn("a?[2Jb", out)

    def test_under_herdr_the_avatar_is_one_kitty_transmission_of_the_files_bytes(self):
        out = self.run_once("herdr", tty=True)
        self.assertEqual(out.count(f"{ESC}_Ga=T"), 1)
        self.assertNotIn("▀", out)
        self.assertIn("a?[2Jb", out)


if __name__ == "__main__":
    unittest.main()
