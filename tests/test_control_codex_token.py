#!/usr/bin/env python3
"""tools/fabric/control/codex_token.py (agent-fabric ADR-053 rule 8): `fabric-accounts codex-token` and the
coordinator's refresh timer. The three programs it runs — `fabric-secrets` (the store half), `fabric-ctl` (the sync
half) and `codex` (the refresh) — are fakes that record their argv and environment, run as real subprocesses; the
sign-in is a fake of the real shape with sentinel refresh and id tokens.

Each case fails when its guard is removed: no value in any argv or environment a program is given; humans and unknown
logins refused before anything runs; a refusal before any row becomes a failed row with its reason; only the logins
the store reached are synced; the refresh runs only under 72 h, in a minimal environment, and a refresh that does not
advance the expiry distributes nothing; the tick says an absent sign-in once a day, never distributes a fresh one,
and reports what it did."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "control"))
from chatgpt_fixtures import ID_TOKEN, REFRESH, fake_jwt, write_signin  # noqa: E402
from control import codex_token as ct  # noqa: E402

PROGRAM = """#!%(python)s
import json, os, sys
state = %(state)r
name = os.path.basename(sys.argv[0])
with open(os.path.join(state, name + ".calls"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd()}) + "\\n")
%(body)s
"""
STORE_BODY = """
rows = os.path.join(state, "rows.json")
if os.path.exists(rows):
    sys.stdout.write(open(rows).read())
fail = os.path.join(state, "store-fail")
if os.path.exists(fail):
    sys.stderr.write(open(fail).read())
    sys.exit(1)
code = os.path.join(state, "store-exit")
if os.path.exists(code):
    sys.exit(int(open(code).read()))
"""
CTL_BODY = """
sys.exit(int(open(os.path.join(state, "ctl-exit")).read()) if os.path.exists(os.path.join(state, "ctl-exit")) else 0)
"""
CODEX_BODY = """
mode = open(os.path.join(state, "codex-mode")).read().strip() if os.path.exists(os.path.join(state, "codex-mode")) else "advance"
if mode == "advance":
    import shutil
    dest = os.path.join(os.environ["CODEX_HOME"], "auth.json")
    shutil.copy(os.path.join(state, "new-auth.json"), dest)
    os.chmod(dest, 0o600)
sys.exit(7 if mode == "fail" else 0)
"""
LOGINS = ["python-dev-01", "rust-dev-01", "architect-cto-01"]
HUMANS = ["owner"]


class Fakes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="codex-token-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "root")
        self.state = os.path.join(self.tmp, "state")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.root, "bin"))
        os.makedirs(self.state)
        self.signin_dir = os.path.join(self.home, ".codex-chatgpt")
        for name, body in (("fabric-secrets", STORE_BODY), ("fabric-ctl", CTL_BODY)):
            self.program(os.path.join(self.root, "bin", name), body)
        self.fakebin = os.path.join(self.tmp, "fakebin")
        os.makedirs(self.fakebin)
        self.program(os.path.join(self.fakebin, "codex"), CODEX_BODY)
        self.env = {"HOME": self.home, "PATH": f"{self.fakebin}:/usr/bin:/bin", "LANG": "C.UTF-8",
                    "GH_TOKEN": "ghp_SESSION_SENTINEL", "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-SESSION_SENTINEL", "AGENT_FABRIC_ROOT": self.root}
        self.out: list[str] = []
        self.said: list[str] = []
        self.now = time.time()
        self.write_signin(self.now + 200 * 3600)

    def program(self, path, body):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(PROGRAM % {"python": sys.executable, "body": body, "state": self.state})
        os.chmod(path, 0o755)

    def write_signin(self, exp):
        write_signin(self.signin_dir, int(exp))

    def calls(self, name):
        path = os.path.join(self.state, name + ".calls")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh]

    def rows(self, *rows):
        with open(os.path.join(self.state, "rows.json"), "w", encoding="utf-8") as fh:
            json.dump(list(rows), fh)

    def agents(self):
        return LOGINS, HUMANS

    def main(self, *argv):
        return ct.main(argv, env=self.env, root=self.root, agents=self.agents, say=self.said.append, out=self.out.append)

    def written(self, *logins):
        self.rows(*({"login": lg, "status": "written", "token_sha256_12": "a" * 12} for lg in logins))


class Command(Fakes):
    def test_all_means_every_placed_agent_never_a_human_and_each_is_synced(self):
        self.written(*LOGINS)
        self.assertEqual(self.main("all"), 0)
        (store,) = self.calls("fabric-secrets")
        self.assertEqual(store["argv"], ["store", "codex-assign", *LOGINS, "--home", self.signin_dir, "--json"])
        (ctl,) = self.calls("fabric-ctl")
        self.assertEqual(ctl["argv"], [*LOGINS, "secrets-sync"])
        self.assertNotIn("owner", store["argv"] + ctl["argv"])
        self.assertTrue(all("written" in line for line in self.out), self.out)

    def test_no_value_is_in_any_argument_or_in_what_is_printed_or_said(self):
        self.written("python-dev-01")
        access = fake_jwt(int(self.now) + 200 * 3600)
        self.main("python-dev-01")
        everything = json.dumps([c["argv"] for c in self.calls("fabric-secrets") + self.calls("fabric-ctl")]) + "\n".join(self.out + self.said)
        for secret in (access, REFRESH, ID_TOKEN):
            self.assertNotIn(secret, everything)

    def test_a_human_and_an_unknown_login_are_refused_before_anything_runs(self):
        for named, want in (("owner", "human login"), ("nobody-here", "not a placed account")):
            with self.subTest(named):
                self.said.clear()
                self.assertEqual(self.main(named), 2)
                self.assertIn(want, self.said[0])
        self.assertEqual((self.calls("fabric-secrets"), self.calls("fabric-ctl")), ([], []))

    def test_usage_errors_are_exit_2_and_run_nothing(self):
        for argv in ((), ("--bogus", "all"), ("--no-sync",)):
            with self.subTest(argv=argv):
                self.assertEqual(self.main(*argv), 2)
        self.assertEqual(self.calls("fabric-secrets"), [])

    def test_no_sync_writes_the_store_and_says_the_login_applies_it_later(self):
        self.written("python-dev-01")
        self.assertEqual(self.main("python-dev-01", "--no-sync"), 0)
        self.assertEqual(self.calls("fabric-ctl"), [])
        self.assertIn("next fabric-secrets sync", self.said[0])

    def test_force_is_passed_to_the_store(self):
        self.written("python-dev-01")
        self.main("python-dev-01", "--force")
        self.assertIn("--force", self.calls("fabric-secrets")[0]["argv"])

    def test_only_the_logins_the_store_reached_are_synced_and_a_failed_row_is_exit_1(self):
        self.rows({"login": "python-dev-01", "status": "unchanged", "token_sha256_12": "b" * 12},
                  {"login": "rust-dev-01", "status": "failed", "reason": "no mirror"})
        self.assertEqual(self.main("python-dev-01", "rust-dev-01"), 1)
        self.assertEqual(self.calls("fabric-ctl")[0]["argv"], ["python-dev-01", "secrets-sync"], "the unchanged one too")

    def test_a_refusal_before_any_row_is_a_failed_row_with_its_reason_and_no_sync(self):
        with open(os.path.join(self.state, "store-fail"), "w", encoding="utf-8") as fh:
            fh.write("noise\nfabric-secrets store: the sign-in's access token has expired; nothing written\n")
        self.assertEqual(self.main("python-dev-01"), 1)
        self.assertIn("has expired; nothing written", self.out[0])
        self.assertEqual(self.calls("fabric-ctl"), [])

    def test_a_sync_that_fails_is_exit_1(self):
        self.written("python-dev-01")
        with open(os.path.join(self.state, "ctl-exit"), "w", encoding="utf-8") as fh:
            fh.write("3")
        self.assertEqual(self.main("python-dev-01"), 1)


class StoreStatus(Fakes):
    """The store command's exit status is read beside its rows (review of #232, claim 4)."""

    def exit_code(self, n):
        with open(os.path.join(self.state, "store-exit"), "w", encoding="utf-8") as fh:
            fh.write(str(n))

    def test_a_non_zero_exit_with_an_empty_list_is_a_failure_with_a_row_per_login(self):
        self.rows()
        self.exit_code(1)
        self.assertEqual(self.main("python-dev-01", "rust-dev-01"), 1)
        self.assertEqual(len(self.out), 2)
        self.assertTrue(all("failed" in line for line in self.out), self.out)
        self.assertEqual(self.calls("fabric-ctl"), [])

    def test_a_login_the_store_gave_no_row_for_is_failed_and_the_others_are_still_synced(self):
        self.rows({"login": "python-dev-01", "status": "written", "token_sha256_12": "c" * 12})
        self.assertEqual(self.main("python-dev-01", "rust-dev-01"), 1)
        self.assertIn("rust-dev-01", " ".join(self.out))
        self.assertEqual(self.calls("fabric-ctl")[0]["argv"], ["python-dev-01", "secrets-sync"])

    def test_a_non_zero_exit_beside_rows_that_all_succeeded_is_a_failure_but_the_successes_sync(self):
        self.written("python-dev-01")
        self.exit_code(1)
        self.assertEqual(self.main("python-dev-01"), 1)
        self.assertIn("exited non-zero though every row succeeded", self.said[0])
        self.assertEqual(self.calls("fabric-ctl")[0]["argv"], ["python-dev-01", "secrets-sync"])

    def test_a_zero_exit_beside_a_failed_row_is_a_failure_too(self):
        self.rows({"login": "python-dev-01", "status": "failed", "reason": "no mirror"})
        self.assertEqual(self.main("python-dev-01"), 1)

    def test_rows_without_a_login_are_no_rows(self):
        self.rows({"status": "written"})
        self.exit_code(0)
        self.assertEqual(self.main("python-dev-01"), 1)
        self.assertIn("failed", self.out[0])
        self.out.clear()
        self.rows({"status": "written"}, "not a row")
        self.exit_code(0)
        self.assertEqual(self.main("python-dev-01"), 1)
        self.assertIn("failed", self.out[0])

    def test_one_malformed_row_costs_the_valid_ones_nothing_and_a_row_for_nobody_asked_is_dropped(self):
        self.rows({"login": "python-dev-01", "status": "written", "token_sha256_12": "d" * 12}, {"status": "written"},
                  {"login": "zzz-not-asked", "status": "written"}, {"login": "rust-dev-01"})
        self.exit_code(0)
        self.assertEqual(self.main("python-dev-01", "rust-dev-01"), 1)
        self.assertEqual(self.calls("fabric-ctl")[0]["argv"], ["python-dev-01", "secrets-sync"], "the valid row's login is synced")
        text = "\n".join(self.out)
        self.assertIn("rust-dev-01", text)
        self.assertNotIn("zzz-not-asked", text + json.dumps(self.calls("fabric-ctl")))

    def test_the_default_root_is_the_checkout_that_holds_bin_fabric_secrets(self):
        self.assertTrue(os.path.isfile(os.path.join(ct.FABRIC, "bin", "fabric-secrets")), ct.FABRIC)
        self.assertEqual(ct.FABRIC, HERE)
        seen = []

        class Ticker:
            def __init__(self, name, fn, every_s, first_s=0.0):
                seen.append(fn)

            def start(self):
                return self
        saved = os.environ.pop("AGENT_FABRIC_ROOT", None)
        try:
            ct.start(Ticker, lambda m: None, agents=lambda: LOGINS, env={})
        finally:
            if saved is not None:
                os.environ["AGENT_FABRIC_ROOT"] = saved
        self.assertEqual(seen[0].root, HERE)


class Refresh(Fakes):
    def new_auth(self, exp):
        scratch = os.path.join(self.tmp, "new")
        write_signin(scratch, int(exp))
        shutil.copy(os.path.join(scratch, "auth.json"), os.path.join(self.state, "new-auth.json"))

    def test_under_72_hours_it_refreshes_in_a_minimal_environment_and_then_distributes(self):
        self.write_signin(self.now + 10 * 3600)
        self.new_auth(self.now + 240 * 3600)
        self.written("python-dev-01")
        self.assertEqual(self.main("python-dev-01", "--refresh"), 0)
        (call,) = self.calls("codex")
        self.assertEqual(call["argv"], ["exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", ct.PROMPT])
        self.assertEqual(call["env"]["CODEX_HOME"], self.signin_dir)
        for leaked in ("GH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "AGENT_FABRIC_ROOT"):
            self.assertNotIn(leaked, call["env"], "the session's environment stays out")
        self.assertNotEqual(call["cwd"], self.home, "run in a scratch directory")
        self.assertEqual(len(self.calls("fabric-secrets")), 1)

    def test_over_72_hours_it_does_not_refresh(self):
        self.written("python-dev-01")
        self.assertEqual(self.main("python-dev-01", "--refresh"), 0)
        self.assertEqual(self.calls("codex"), [])

    def test_a_refresh_that_does_not_advance_the_expiry_distributes_nothing(self):
        self.write_signin(self.now + 10 * 3600)
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("noop")
        self.assertEqual(self.main("python-dev-01", "--refresh"), 1)
        self.assertIn("did not advance", self.said[0])
        self.assertEqual(self.calls("fabric-secrets"), [])

    def test_a_codex_that_fails_or_is_missing_says_why_and_distributes_nothing(self):
        self.write_signin(self.now + 10 * 3600)
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("fail")
        self.assertEqual(self.main("python-dev-01", "--refresh"), 1)
        self.assertIn("exited 7", self.said[0])
        self.said.clear()
        self.env["PATH"] = "/usr/bin:/bin"
        self.assertEqual(self.main("python-dev-01", "--refresh"), 1)
        self.assertIn("no `codex` on PATH", self.said[0])
        self.assertEqual(self.calls("fabric-secrets"), [])


class Timer(Fakes):
    def tick(self, clock=None, **kw):
        self.logs: list[str] = []
        return ct.Tick(env=self.env, root=self.root, agents=lambda: LOGINS, log=self.logs.append, clock=clock or time.time, **kw)

    def test_a_missing_sign_in_is_said_once_a_day_and_nothing_runs(self):
        shutil.rmtree(self.signin_dir)
        now = [self.now]
        tick = self.tick(clock=lambda: now[0])
        self.assertEqual(tick(), "absent")
        first = list(self.logs)
        self.assertEqual(len(first), 1)
        self.assertIn("no sign-in at", first[0])
        now[0] += 3600
        self.assertEqual(tick(), "absent")
        self.assertEqual(self.logs, first, "not again within the day")
        now[0] += 24 * 3600
        tick()
        self.assertEqual(len(self.logs), 2)
        self.assertEqual((self.calls("codex"), self.calls("fabric-secrets")), ([], []))

    def test_a_fresh_sign_in_is_never_refreshed_but_handed_out_at_the_first_tick_and_then_once_a_day(self):
        self.written(*LOGINS)
        now = [self.now]
        tick = self.tick(clock=lambda: now[0])
        self.assertEqual(tick(), "distributed")
        self.assertEqual(self.calls("codex"), [], "fresh: Codex is not run")
        self.assertEqual(len(self.calls("fabric-secrets")), 1)
        now[0] += 6 * 3600
        self.assertEqual(tick(), "fresh")
        self.assertEqual(len(self.calls("fabric-secrets")), 1, "not again within the day")
        now[0] += 19 * 3600
        self.assertEqual(tick(), "distributed")
        self.assertEqual(len(self.calls("fabric-secrets")), 2, "a day on: a login placed since takes it")

    def test_a_distribution_that_missed_a_login_is_tried_again_at_the_next_tick(self):
        self.rows({"login": "python-dev-01", "status": "failed", "reason": "no mirror"})
        now = [self.now]
        tick = self.tick(clock=lambda: now[0])
        self.assertEqual(tick(), "failed")
        self.assertIn("tried again at the next tick", self.logs[-1])
        self.written(*LOGINS)
        now[0] += 600
        self.assertEqual(tick(), "distributed")
        self.assertEqual(len(self.calls("fabric-secrets")), 2)
        now[0] += 600
        self.assertEqual(tick(), "fresh", "reached everyone: the retry is over")

    def test_an_old_sign_in_is_refreshed_and_distributed_to_every_agent_and_said_without_a_value(self):
        self.write_signin(self.now + 5 * 3600)
        scratch = os.path.join(self.tmp, "new")
        write_signin(scratch, int(self.now + 240 * 3600))
        shutil.copy(os.path.join(scratch, "auth.json"), os.path.join(self.state, "new-auth.json"))
        self.written(*LOGINS)
        tick = self.tick()
        self.assertEqual(tick(), "distributed")
        self.assertEqual(self.calls("fabric-secrets")[0]["argv"][:5], ["store", "codex-assign", *LOGINS])
        self.assertEqual(self.calls("fabric-ctl")[0]["argv"], [*LOGINS, "secrets-sync"])
        self.assertEqual(len(self.logs), 1)
        for secret in (fake_jwt(int(self.now + 240 * 3600)), REFRESH, ID_TOKEN):
            self.assertNotIn(secret, self.logs[0])

    def test_each_way_it_can_go_wrong_is_said_and_names_what_did_not_happen(self):
        self.write_signin(self.now + 5 * 3600)
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("fail")
        tick = self.tick()
        tick.distributed_at = self.now            # just handed out: not due, so a refresh that gives nothing hands out nothing
        self.assertEqual(tick(), "refused")
        self.assertIn("could not be refreshed", self.logs[0])
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("noop")
        t2 = self.tick()
        t2.distributed_at = self.now
        self.assertEqual(t2(), "unchanged-expiry")
        self.assertEqual(self.calls("fabric-secrets"), [], "nothing distributed on either")
        scratch = os.path.join(self.tmp, "new")
        write_signin(scratch, int(self.now + 240 * 3600))
        shutil.copy(os.path.join(scratch, "auth.json"), os.path.join(self.state, "new-auth.json"))
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("advance")
        self.rows({"login": "python-dev-01", "status": "failed", "reason": "no mirror"})
        t = self.tick()
        self.assertEqual(t(), "failed")
        self.assertIn("not every login took it", self.logs[-1])

    def test_a_login_that_missed_a_distribution_still_gets_the_sign_in_when_the_refresh_gives_nothing_new(self):
        self.write_signin(self.now + 30 * 3600)           # under 72 h, over the one-hour floor
        self.rows({"login": "python-dev-01", "status": "failed", "reason": "no mirror"})
        now = [self.now]
        tick = self.tick(clock=lambda: now[0])
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("noop")
        self.assertEqual(tick(), "unchanged-expiry")                       # the first tick: catch-up is due, the refresh is a no-op
        self.assertEqual(len(self.calls("fabric-secrets")), 1, "handed out anyway")
        self.assertTrue(tick.pending)
        self.written(*LOGINS)
        now[0] += 600
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("fail")
        self.assertEqual(tick(), "refused")                                # a refresh that fails: the retry still happens
        self.assertEqual(len(self.calls("fabric-secrets")), 2)
        self.assertFalse(tick.pending)
        now[0] += 600
        self.assertEqual(tick(), "refused")
        self.assertEqual(len(self.calls("fabric-secrets")), 2, "reached everyone and not due again: nothing handed out")

    def test_under_the_one_hour_floor_nothing_is_handed_out_even_when_due(self):
        self.write_signin(self.now + 1800)
        with open(os.path.join(self.state, "codex-mode"), "w", encoding="utf-8") as fh:
            fh.write("fail")
        self.assertEqual(self.tick()(), "refused")
        self.assertEqual(self.calls("fabric-secrets"), [])

    def test_start_registers_one_timer_with_a_first_run_soon_after_the_daemon_starts(self):
        seen = []

        class Ticker:
            def __init__(self, name, fn, every_s, first_s=0.0):
                seen.append((name, every_s, first_s, callable(fn)))

            def start(self):
                seen.append("started")
                return self
        ct.start(Ticker, lambda m: None, agents=lambda: LOGINS, env=self.env, root=self.root)
        self.assertEqual(seen, [("codex sign-in", ct.TICK_S, ct.FIRST_TICK_S, True), "started"])


if __name__ == "__main__":
    unittest.main()
