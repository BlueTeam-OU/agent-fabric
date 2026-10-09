#!/usr/bin/env python3
"""fabric-accounts (tools/fabric/control/accounts.py): the setup and the local
look at the observed Claude accounts. No token ever reaches the output; login
needs a terminal and a valid account name, and runs the harness in that
account's own config directory with no inherited token. A port of
runtime/control/tests/accounts.test.mjs case for case. `placements` is
control/ctl.py's (python-dev-03): handed in as the rows it returns."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import accounts as A  # noqa: E402
from control.ops.usage import accounts_dir  # noqa: E402

ACCESS, REFRESH = "sk-ant-oat01-ACCESS-VALUE", "sk-ant-ort01-REFRESH-VALUE"


def fp(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def ms(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() * 1000


class Base(unittest.TestCase):
    def tmp(self) -> str:
        t = tempfile.TemporaryDirectory(prefix="accounts-")
        self.addCleanup(t.cleanup)
        return t.name

    def capture(self, fn):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fn()
        return code, out.getvalue(), err.getvalue()


def sign_in(d: str, expires_at=None, refresh: bool = True, email: str = "a@example.org", **extra) -> None:
    os.makedirs(d, exist_ok=True)
    oauth = {"accessToken": ACCESS, **({"refreshToken": REFRESH} if refresh else {}), **({"expiresAt": expires_at} if expires_at is not None else {}), **extra}
    with open(os.path.join(d, ".credentials.json"), "w", encoding="utf-8") as fh:
        json.dump({"claudeAiOauth": oauth}, fh)
    with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as fh:
        json.dump({"oauthAccount": {"emailAddress": email}}, fh)


class ListAndLogin(Base):
    def test_list_in_words_and_never_a_token(self):
        h = self.tmp()
        d = accounts_dir(h, {})
        now = ms("2026-09-24T20:00:00Z")
        sign_in(os.path.join(d, "claude-live"), now + 3600e3)
        sign_in(os.path.join(d, "claude-lapsed"), now - 60e3, email="b@example.org")
        sign_in(os.path.join(d, "claude-norefresh"), now + 3600e3, refresh=False, email="c@example.org")
        os.makedirs(os.path.join(d, "claude-new"))
        lines = "\n".join(A.list_lines(d, now))
        self.assertRegex(lines, r"claude-lapsed\s+b@example\.org\s+sign-in lapsed at 2026-09-24T19:59:00\.000Z \(the next read renews it\)")
        self.assertRegex(lines, r"claude-live\s+a@example\.org\s+signed in until 2026-09-24T21:00:00\.000Z")
        self.assertRegex(lines, r"claude-new\s+-\s+not signed in")
        self.assertRegex(lines, r"claude-norefresh\s+c@example\.org\s+signed in, NO refresh token")
        self.assertTrue(ACCESS not in lines and REFRESH not in lines, "a token reached the output")
        self.assertEqual(sorted(A.describe(os.path.join(d, "claude-live"), now)), ["email", "expired", "expires_at", "refresh_token", "signed_in", "slug"])
        code, out, _ = self.capture(lambda: A.main(["list"], home=h, env={}))
        self.assertEqual(code, 0)
        self.assertIn("claude-live", out)
        self.assertRegex("\n".join(A.list_lines(accounts_dir(self.tmp(), {}))), r"no Claude account observed .* fabric-accounts login <account>")

    def test_describe_does_not_invent_an_expiry(self):
        d = os.path.join(self.tmp(), "claude-x")
        for stored, expect in ((None, (None, None)), ("soon", (None, None)), (1e30, (None, None)), (0, ("1970-01-01T00:00:00.000Z", True))):
            sign_in(d, stored)
            r = A.describe(d, 1000)
            self.assertEqual((r["expires_at"], r["expired"]), expect, stored)

    def test_login(self):
        h = self.tmp()
        env = {"PATH": "/usr/bin", "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-inherited", "ANTHROPIC_API_KEY": "sk-ant-api-x", "KEEP": "yes"}

        def never(*_a, **_k):
            raise AssertionError("no harness")
        code, _, _ = self.capture(lambda: A.main(["login", "Not/A Name"], home=h, env=env, stdin_tty=True, spawn=never))
        self.assertEqual(code, 2)
        code, _, err = self.capture(lambda: A.main(["login", "claude-a"], home=h, env=env, stdin_tty=False, spawn=never))
        self.assertEqual(code, 2)
        self.assertIn("real terminal", err)
        target = os.path.join(accounts_dir(h, env), "claude-a")
        seen: dict = {}

        def harness(cmd, **kw):
            seen.update(kw)
            sign_in(target, ms("2026-09-24T20:00:00Z") + 8 * 3600e3)
            return subprocess.CompletedProcess(cmd, 0)
        code, _, err = self.capture(lambda: A.main(["login", "claude-a"], home=h, env=env, stdin_tty=True, spawn=harness))
        self.assertEqual(code, 0, err)
        self.assertEqual(seen["env"]["CLAUDE_CONFIG_DIR"], target)
        self.assertEqual(seen["cwd"], target)
        self.assertTrue("CLAUDE_CODE_OAUTH_TOKEN" not in seen["env"] and "ANTHROPIC_API_KEY" not in seen["env"], "an inherited token reached the login harness")
        self.assertEqual(seen["env"]["KEEP"], "yes", "the rest of the environment is kept (a terminal needs it)")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o700)
        self.assertRegex(err, r"claude-a signed in as a@example\.org")
        held = os.path.join(accounts_dir(h, env), "claude-held")
        os.makedirs(held)
        with open(os.path.join(held, ".fabric-read.lock"), "w", encoding="utf-8") as fh:
            fh.write(f"{os.getppid()}\n")
        code, _, err = self.capture(lambda: A.main(["login", "claude-held"], home=h, env=env, stdin_tty=True, spawn=never))
        self.assertEqual(code, 1)
        self.assertIn("being read right now", err)
        self.assertNotIn("opens now", err, "a refused login never tells the operator to go to the browser")
        self.assertFalse(os.path.exists(os.path.join(target, ".fabric-read.lock")), "login released its lock")
        code, _, err = self.capture(lambda: A.main(["login", "claude-b"], home=h, env=env, stdin_tty=True,
                                                   spawn=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0)))
        self.assertEqual(code, 1, "a harness closed without /login is not a success")
        self.assertIn("not signed in", err)

    def test_login_tightens_a_directory_that_already_exists(self):
        h = self.tmp()
        pre = os.path.join(accounts_dir(h, {}), "claude-c")
        os.makedirs(pre)
        os.chmod(pre, 0o755)
        self.capture(lambda: A.main(["login", "claude-c"], home=h, env={}, stdin_tty=True, spawn=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0)))
        self.assertEqual(os.stat(pre).st_mode & 0o777, 0o700)

    def test_login_releases_its_lock_when_the_harness_cannot_start(self):
        h = self.tmp()
        env: dict[str, str] = {}

        def missing(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        with self.assertRaises(FileNotFoundError):
            self.capture(lambda: A.main(["login", "claude-a"], home=h, env=env, stdin_tty=True, spawn=missing))
        self.assertFalse(os.path.exists(os.path.join(accounts_dir(h, env), "claude-a", ".fabric-read.lock")))

    def test_read(self):
        h = self.tmp()

        def read(home, directory=None):
            return {"status": "ok", "accounts": [
                {"slug": "claude-a", "email": "a@example.org", "status": "ok", "limits": [
                    {"kind": "session", "percent": 11, "resets_at": "2026-09-24T18:49:59Z"},
                    {"kind": "weekly_scoped", "percent": 86, "resets_at": "2026-09-28T15:59:59Z", "model": "Opus"}]},
                {"slug": "claude-b", "email": None, "status": "failed", "error": "Failed to refresh OAuth token"}]}
        code, out, _ = self.capture(lambda: A.main(["read"], home=h, env={}, read=read))
        self.assertEqual(code, 1)
        self.assertRegex(out, r"a@example\.org\s+ok\s+session 11% resets 2026-09-24T18:49; weekly_scoped 86% \(Opus\) resets 2026-09-28T15:59")
        self.assertRegex(out, r"claude-b\s+failed\s+Failed to refresh OAuth token")
        code, out, _ = self.capture(lambda: A.main(["read"], home=h, env={}, read=lambda home, directory=None: {"status": "none"}))
        self.assertEqual(code, 1)
        self.assertIn("no Claude account observed", out)
        self.assertEqual(self.capture(lambda: A.main(["bogus"], home=h, env={}))[0], 2)
        self.assertEqual(self.capture(lambda: A.main(["list", "extra"], home=h, env={}))[0], 2)


class FakeStore:
    """The coordinator's store, faked at the command fabric-accounts runs:
    `fabric-secrets store templates|assign … --json`. It keeps the value in
    its own process, so only fingerprints and rows come back."""

    def __init__(self) -> None:
        self.tpl = {"claude-a": "sk-ant-oat01-A", "claude-b": "sk-ant-oat01-B", "claude-empty": ""}
        self.on = {"flutter-dev-01": "none", "db-admin": "none", "web-dev-01": "claude-a"}
        self.calls: list[str] = []

    def run(self, cmd, **kw):
        assert os.path.basename(cmd[0]) == "fabric-secrets", "nothing but the store is asked"
        assert kw.get("timeout") and kw.get("check") is True, kw
        args = cmd[1:]
        self.calls.append(" ".join(args))
        if args[1] == "templates":
            return subprocess.CompletedProcess(cmd, 0, json.dumps([{"account": a, "token_sha256_12": fp(v) if v else None} for a, v in self.tpl.items()]).encode(), b"")
        account, *rest = args[2:]
        rows = []
        for login in (a for a in rest if a not in ("--json", "--force")):
            frm = self.on.get(login)
            if frm == account:
                rows.append({"login": login, "from": frm, "to": account, "status": "unchanged"})
            else:
                self.on[login] = account
                rows.append({"login": login, "from": frm, "to": account, "status": "written"})
        return subprocess.CompletedProcess(cmd, 0, json.dumps(rows).encode(), b"")


def placed(*humans: str):
    logins = ["flutter-dev-01", "db-admin", "web-dev-01", *humans]
    return lambda registry: [{"login": lg, "kind": "human" if lg in humans else "agent"} for lg in logins]


class Assign(Base):
    def go(self, argv, store, spawn, placements=None):
        return self.capture(lambda: A.main(argv, home=self.tmp(), env={}, run=store.run, spawn=spawn, placements=placements or placed()))

    def test_templates_by_fingerprint_none_clean_when_one_lacks_a_token_no_value_printed(self):
        d = FakeStore()
        code, out, _ = self.capture(lambda: A.main(["templates"], home=self.tmp(), env={}, run=d.run))
        self.assertEqual(code, 1, "a template without a token is not a clean answer")
        self.assertRegex(out, rf"claude-a\s+setup-token {fp('sk-ant-oat01-A')}")
        self.assertRegex(out, r"claude-empty\s+no CLAUDE_CODE_OAUTH_TOKEN")
        self.assertNotIn("sk-ant-oat01", out)
        self.assertEqual(d.calls, ["store templates --json"])
        d.tpl = {"claude-a": "x"}
        self.assertEqual(self.capture(lambda: A.main(["templates"], home=self.tmp(), env={}, run=d.run))[0], 0)
        d.tpl = {}
        code, out, _ = self.capture(lambda: A.main(["templates"], home=self.tmp(), env={}, run=d.run))
        self.assertEqual(code, 1)
        self.assertIn("no template in this store", out)

    def test_assign_writes_each_store_leaves_one_already_there_and_every_named_login_syncs_proves_and_restarts(self):
        d = FakeStore()
        synced: list = []

        def spawn(cmd, **kw):
            assert kw.get("timeout"), "a call to a program has a bound"
            synced[:] = [os.path.basename(cmd[0]), *cmd[1:]]
            return subprocess.CompletedProcess(cmd, 0)
        code, out, err = self.go(["assign", "flutter-dev-01", "web-dev-01", "claude-b"], d, spawn)
        self.assertEqual(code, 0, err + out)
        self.assertEqual((d.on["flutter-dev-01"], d.on["web-dev-01"]), ("claude-b", "claude-b"))
        self.assertRegex(out, r"flutter-dev-01\s+none\s+→ claude-b\s+written")
        self.assertRegex(out, r"web-dev-01\s+claude-a\s+→ claude-b\s+written")
        self.assertEqual(synced, ["fabric-ctl", "flutter-dev-01", "web-dev-01", "secrets-sync", "--expect", fp("sk-ant-oat01-B"), "--restart"])
        self.assertNotIn("sk-ant-oat01", out, "no template token in the output")
        synced.clear()
        code, out, _ = self.go(["assign", "flutter-dev-01", "claude-b", "--no-restart"], d, spawn)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"flutter-dev-01\s+claude-b\s+→ claude-b\s+unchanged")
        self.assertEqual(synced, ["fabric-ctl", "flutter-dev-01", "secrets-sync", "--expect", fp("sk-ant-oat01-B")],
                         "unchanged in the store, still proved on the account; --no-restart leaves its session alone")
        code, _, _ = self.go(["assign", "flutter-dev-01", "claude-b"], d, lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1))
        self.assertEqual(code, 1, "an account that did not prove the move fails the command")
        code, _, err = self.go(["assign", "flutter-dev-01", "claude-b"], d, lambda cmd, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd, 1)))
        self.assertEqual(code, 1, "a fabric-ctl that never answers is a failure, said")
        self.assertIn("fabric-accounts: Command failed", err)

    def test_a_human_login_is_never_given_a_claude_account_named_or_under_all(self):
        d = FakeStore()
        pl = placed("deck-human")

        def never(*_a, **_k):
            raise AssertionError("no sync")
        code, _, err = self.go(["assign", "deck-human", "claude-b"], d, never, pl)
        self.assertEqual(code, 2)
        self.assertIn("a human login has no Claude account (ADR-044): deck-human", err)
        synced: list = []
        code, out, err = self.go(["assign", "all", "claude-b"], d, lambda cmd, **kw: (synced.extend(cmd), subprocess.CompletedProcess(cmd, 0))[1], pl)
        self.assertEqual(code, 0, err + out)
        self.assertTrue(d.on["db-admin"] == "claude-b" and "deck-human" not in d.on, "all is every agent, not the human")
        self.assertNotIn("deck-human", synced)

    def test_refusals_before_anything_is_written(self):
        d = FakeStore()

        def never(*_a, **_k):
            raise AssertionError("no sync")
        for argv, pattern in ((["assign", "web-dev-01", "own"], r"runs only on a template's token"), (["assign", "nobody", "claude-b"], r"not a placed account"),
                              (["assign", "db-admin", "claude-zzz"], r"not a template"), (["assign", "db-admin", "claude-empty"], r"holds no CLAUDE_CODE_OAUTH_TOKEN"),
                              (["assign", "claude-b"], r"^usage: fabric-accounts")):
            code, _, err = self.go(argv, d, never)
            self.assertEqual(code, 2, argv)
            self.assertRegex(err, pattern)
        self.assertFalse(any(c.startswith("store assign") for c in d.calls), "a refusal writes nothing")

    def test_a_failed_row_is_still_a_row_and_fails_the_run_no_sync_syncs_nothing(self):
        calls: list[str] = []

        def run(cmd, **kw):
            calls.append(" ".join(cmd[1:]))
            if cmd[2] == "templates":
                return subprocess.CompletedProcess(cmd, 0, json.dumps([{"account": "work", "token_sha256_12": "abcdef012345"}]).encode(), b"")
            raise subprocess.CalledProcessError(1, cmd, json.dumps([{"login": "a", "status": "written"}, {"login": "b", "status": "failed", "reason": "no committed key for b"}]).encode(), b"")
        self.assertEqual(A.store_templates(run, "/r"), [{"account": "work", "token_sha256_12": "abcdef012345"}])
        self.assertEqual([r["status"] for r in A.store_assign(["a", "b"], "work", run, True, "/r")], ["written", "failed"])
        self.assertEqual(calls, ["store templates --json", "store assign work a b --force --json"])

        def never(*_a, **_k):
            raise AssertionError("no sync")
        pl = lambda registry: [{"login": "a", "kind": "agent"}, {"login": "b", "kind": "agent"}]  # noqa: E731
        code, out, err = self.capture(lambda: A.main(["assign", "a", "b", "work", "--no-sync"], home=self.tmp(), env={}, run=run, spawn=never, placements=pl))
        self.assertEqual(code, 1, out + err)
        self.assertRegex(out, r"b .* failed  no committed key for b")
        self.assertIn("--no-sync — each changed login applies it at its next fabric-secrets sync", err)

    def test_a_store_that_fails_without_rows_fails_every_login_with_the_last_line_of_stderr(self):
        def run(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, b"", b"first\nfabric-secrets: the store is locked\n")
        rows = A.store_assign(["a", "b"], "work", run, False, "/r")
        self.assertEqual(rows, [{"login": lg, "status": "failed", "reason": "fabric-secrets: the store is locked"} for lg in ("a", "b")])

        def gone(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        self.assertEqual([r["reason"] for r in A.store_assign(["a"], "work", gone, False, "/r")], ["spawn fabric-secrets ENOENT"])


if __name__ == "__main__":
    unittest.main()
