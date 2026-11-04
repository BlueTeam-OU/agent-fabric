#!/usr/bin/env python3
"""fabric-accounts observe (tools/fabric/control/account_observe.py) and the probe it reads
(control/ops/usage.py probe_account): one key, "observed", set in the owner's account file and every other byte
kept; a failed read says so and carries no figures; no token reaches any output. The probe, the store and the
sign-in read are faked at their seams; the facts are those of docs/live-checks/2026-10-24-account-metadata-from-api.md."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import account_observe as O  # noqa: E402
from control import accounts as A  # noqa: E402
import control.ops.usage  # noqa: E402,F401

U = sys.modules["control.ops.usage"]

TOKEN_A, TOKEN_B = "sk-ant-oat01-TEMPLATE-A-SECRET", "sk-ant-oat01-TEMPLATE-B-SECRET"
NOW = 1790280000000.0   # 2026-09-24T20:00:00.000Z

OWNER_FILE = (
    '{\n'
    '    "account": "claude-a",\n'
    '    "plan": "Max 20x",\n'
    '    "renews_on": "17th",\n'
    '    "payment": {"card": "visa \\u2022\\u2022\\u2022\\u2022 4242",   "note": "caf\\u00e9"},\n'
    '    "api_credit": 12.50,\n'
    '    "usage_resets": [1.0, 1e3, true, null]\n'
    '}\n')


def probe_ok(tok: str) -> dict:
    return {"status": "ok", "organization_id": "org-1", "workspace_id": "ws-1",
            "five_hour": {"utilization": 26, "resets_at": "2026-09-24T23:00:00.000Z", "status": "allowed"},
            "seven_day": {"utilization": 76, "resets_at": "2026-10-01T12:00:00.000Z", "status": "allowed_warning"},
            "overage": {"status": "rejected", "disabled_reason": "out_of_credits"}}


class Base(unittest.TestCase):
    def tmp(self) -> str:
        t = tempfile.TemporaryDirectory(prefix="observe-")
        self.addCleanup(t.cleanup)
        return t.name

    def sign_in(self, home: str, slug: str) -> None:
        d = os.path.join(U.accounts_dir(home, {}), slug)
        os.makedirs(d)
        with open(os.path.join(d, ".credentials.json"), "w") as fh:
            json.dump({"claudeAiOauth": {"accessToken": "x"}}, fh)
        with open(os.path.join(d, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"organizationType": "claude_max", "organizationRateLimitTier": "default_claude_max_20x",
                                        "billingType": "stripe_subscription", "subscriptionCreatedAt": "2025-03-17T09:00:00Z",
                                        "hasExtraUsageEnabled": False, "emailAddress": "who@example.org"}}, fh)


class Weekly(unittest.TestCase):
    def test_weekday_and_hour_from_a_header_time_and_from_the_report_s_59_second(self):
        self.assertEqual(O.weekly_reset({"resets_at": "2026-10-01T12:00:00.000Z"}), {"weekday": "thursday", "time_utc": "12:00"})
        self.assertEqual(O.weekly_reset({"resets_at": "2026-09-28T15:59:59Z"}), {"weekday": "monday", "time_utc": "16:00"})
        self.assertEqual(O.weekly_reset({"resets_at": "2026-10-04T23:59:59Z"}), {"weekday": "monday", "time_utc": "00:00"}, "the rounding crosses the day")

    def test_unknown_stays_unknown(self):
        for w in (None, {}, {"resets_at": None}, {"resets_at": "soon"}):
            self.assertIsNone(O.weekly_reset(w))


class SetKey(unittest.TestCase):
    def test_every_other_byte_is_kept_when_the_key_is_added(self):
        out = O.set_key(OWNER_FILE, "observed", {"status": "ok", "n": {"a": [1, 2]}})
        head = OWNER_FILE[:OWNER_FILE.index("\n}")]
        self.assertTrue(out.startswith(head + ",\n    \"observed\": {"), out)
        self.assertTrue(out.endswith("\n}\n"))
        self.assertEqual(json.loads(out)["observed"], {"status": "ok", "n": {"a": [1, 2]}})
        self.assertIn('visa \\u2022\\u2022', out, "an escape is not rewritten as the character")
        self.assertIn("[1.0, 1e3, true, null]", out, "a number is not reformatted")
        self.assertIn('4242",   "note"', out, "odd spacing inside a value is kept")

    def test_an_existing_key_is_replaced_in_place_and_the_rest_kept(self):
        once = O.set_key(OWNER_FILE, "observed", {"status": "ok"})
        twice = O.set_key(once, "observed", {"status": "read-failed", "error": "e"})
        self.assertEqual(twice.count('"observed"'), 1)
        before, after = once.index('"observed"'), twice.index('"observed"')
        self.assertEqual(once[:before], twice[:after])
        self.assertEqual(json.loads(twice)["observed"]["status"], "read-failed")
        self.assertEqual({k: v for k, v in json.loads(twice).items() if k != "observed"}, json.loads(OWNER_FILE))

    def test_key_in_the_middle_keeps_what_follows_it(self):
        text = '{\n  "a": 1,\n  "observed": {"old": true},\n  "z": 2\n}\n'
        out = O.set_key(text, "observed", {"s": 1})
        self.assertTrue(out.endswith(',\n  "z": 2\n}\n'))
        self.assertEqual(json.loads(out), {"a": 1, "observed": {"s": 1}, "z": 2})

    def test_compact_and_empty_objects(self):
        self.assertEqual(O.set_key('{"a":1}', "k", 2), '{"a":1, "k": 2}')
        spaced = O.set_key("{ \t }\n", "k", 1)
        self.assertEqual(json.loads(spaced), {"k": 1})
        self.assertTrue(spaced.endswith(" \t }\n"), "the whitespace inside the braces is kept")
        self.assertEqual(json.loads(O.set_key("{}", "k", {"x": 1})), {"k": {"x": 1}})
        self.assertEqual(json.loads(O.set_key("{\n}\n", "k", 1)), {"k": 1})

    def test_a_file_that_cannot_take_the_key_untouched_is_refused(self):
        for bad in ("", "[]", "{", '{"a": ' + "[" * 200000 + "]" * 200000 + "}", '{"a": 1', '{"a": 1} x', '{"a": NaN}', '{"a" 1}', '{"a": 1,, }', '{"observed": 1, "observed": 2}', "null"):
            with self.assertRaises(O.FileRefused, msg=bad):
                O.set_key(bad, "observed", {})


class Probe(unittest.TestCase):
    def reply(self, status=200, **h):
        base = {"anthropic-ratelimit-unified-5h-utilization": "0.26", "anthropic-ratelimit-unified-5h-reset": "1790290800",
                "anthropic-ratelimit-unified-5h-status": "allowed", "anthropic-ratelimit-unified-7d-utilization": "0.76",
                "anthropic-ratelimit-unified-7d-reset": "1790856000", "anthropic-ratelimit-unified-7d-status": "allowed_warning",
                "anthropic-ratelimit-unified-overage-status": "rejected", "anthropic-ratelimit-unified-overage-disabled-reason": "out_of_credits",
                "anthropic-organization-id": "org-abc", "anthropic-workspace-id": "ws-def"}
        base.update(h)
        return lambda url, **kw: U.Response(status, {k: v for k, v in base.items() if v is not None})

    def test_headers_become_windows_ids_and_overage(self):
        r = U.probe_account(TOKEN_A, self.reply())
        self.assertEqual(r["status"], "ok")
        self.assertEqual((r["five_hour"]["utilization"], r["seven_day"]["utilization"], r["seven_day"]["status"]), (26, 76, "allowed_warning"))
        self.assertEqual((r["organization_id"], r["workspace_id"]), ("org-abc", "ws-def"))
        self.assertEqual(r["overage"], {"status": "rejected", "disabled_reason": "out_of_credits"})

    def test_an_exhausted_account_answers_429_and_is_still_a_reading(self):
        self.assertEqual(U.probe_account(TOKEN_A, self.reply(429))["status"], "ok")

    def test_an_absent_or_misshapen_header_is_none_never_a_default(self):
        r = U.probe_account(TOKEN_A, self.reply(**{"anthropic-organization-id": None, "anthropic-workspace-id": "ws def\r\nx",
                                                    "anthropic-ratelimit-unified-overage-status": None,
                                                    "anthropic-ratelimit-unified-overage-disabled-reason": "Out Of Credits"}))
        self.assertEqual((r["organization_id"], r["workspace_id"], r["overage"]), (None, None, {"status": None, "disabled_reason": None}))

    def test_no_windows_or_no_answer_is_read_failed_and_the_exception_is_dropped(self):
        self.assertEqual(U.probe_account(TOKEN_A, lambda url, **kw: U.Response(403, {})), {"status": "read-failed", "http": 403})

        def boom(url, **kw):
            raise OSError(f"cannot reach with {kw['headers']['Authorization']}")
        r = U.probe_account(TOKEN_A, boom)
        self.assertEqual(r, {"status": "read-failed"})
        self.assertNotIn(TOKEN_A, json.dumps(r))

    def test_a_hostile_utilization_is_none_and_never_infinity_in_the_owners_file(self):
        for bad in ("1e306", "-0.5", "nan", "inf"):
            r = U.probe_account(TOKEN_A, self.reply(**{"anthropic-ratelimit-unified-7d-utilization": bad}))
            self.assertIsNone(r["seven_day"]["utilization"], bad)
        self.assertEqual(U.probe_account(TOKEN_A, self.reply(**{"anthropic-ratelimit-unified-7d-utilization": "0"}))["seven_day"]["utilization"], 0,
                         "positive control: a real zero stays zero")
        with self.assertRaises(ValueError):
            O.set_key("{}", "observed", {"u": float("inf")})
        with self.assertRaises(ValueError):
            O.new_file("a", {"u": float("nan")})

    def test_a_reply_whose_only_headers_normalise_to_nothing_is_read_failed(self):
        only = {"anthropic-ratelimit-unified-5h-utilization": "-1", "anthropic-ratelimit-unified-5h-reset": None,
                "anthropic-ratelimit-unified-7d-utilization": None, "anthropic-ratelimit-unified-7d-reset": "1e15",
                "anthropic-ratelimit-unified-5h-status": None, "anthropic-ratelimit-unified-7d-status": None}
        self.assertEqual(U.probe_account(TOKEN_A, self.reply(401, **only)), {"status": "read-failed", "http": 401})

    def test_an_oversized_hex_header_is_no_reading_and_does_not_abort_the_rest(self):
        r = U.probe_account(TOKEN_A, self.reply(**{"anthropic-ratelimit-unified-7d-utilization": "0x" + "f" * 300}))
        self.assertEqual(r["status"], "ok")
        self.assertIsNone(r["seven_day"]["utilization"] if r["seven_day"] else None)
        self.assertEqual(r["five_hour"]["utilization"], 26)

    def test_a_reset_past_year_9999_is_none_and_the_other_fields_survive(self):
        r = U.probe_account(TOKEN_A, self.reply(**{"anthropic-ratelimit-unified-7d-reset": "1e15"}))
        self.assertEqual(r["status"], "ok")
        self.assertIsNone(r["seven_day"]["resets_at"])
        self.assertEqual(r["seven_day"]["utilization"], 76)

    def test_the_token_is_in_the_one_header_only(self):
        seen = {}

        def fetch(url, **kw):
            seen.update(kw, url=url)
            return U.Response(200, {"anthropic-ratelimit-unified-5h-utilization": "0.1"})
        U.probe_account(TOKEN_A, fetch)
        self.assertEqual(seen["headers"]["Authorization"], f"Bearer {TOKEN_A}")
        self.assertNotIn(TOKEN_A, seen["url"] + json.dumps(json.loads(seen["body"])))


class Main(Base):
    def setUp(self):
        self.home = self.tmp()
        self.store = self.tmp()
        self.puts: list[dict[str, str]] = []
        self.heads: list = []
        self.locks = 0
        self.held_lock = False
        self.token_reads_under_lock: list[bool] = []
        self.head_now = "head-at-read"

    def path_of(self, slug):
        return os.path.join(self.store, f"{slug}.json")

    def put(self, tree, expect_head=None):
        self.heads.append(expect_head)
        files = {}
        for dirpath, _, names in os.walk(tree):
            for n in names:
                with open(os.path.join(dirpath, n), encoding="utf-8") as fh:
                    files[os.path.relpath(os.path.join(dirpath, n), tree)] = fh.read()
        self.puts.append(files)
        for rel, text in files.items():
            with open(self.path_of(os.path.basename(rel)[:-5]), "w", encoding="utf-8") as fh:
                fh.write(text)
        return {"files": list(files), "changed": True, "commit": "abc1234"}

    @contextlib.contextmanager
    def locked(self):
        self.locks += 1
        self.held_lock = True
        try:
            yield self.head_now
        finally:
            self.held_lock = False

    def go(self, argv, tokens=None, probe=probe_ok, read_signin=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = O.main(argv, home=self.home, env={}, tokens=lambda: (self.token_reads_under_lock.append(self.held_lock), tokens if tokens is not None else {"claude-a": TOKEN_A, "claude-b": TOKEN_B})[1],
                          path_of=self.path_of, put=self.put, locked=self.locked, probe=probe,
                          read_signin=read_signin or (lambda d, home=None: {"status": "not-signed-in"}), now=lambda: NOW,
                          say=lambda m: print(m, file=sys.stderr))
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_prints_what_it_would_set_and_touches_nothing(self):
        with open(self.path_of("claude-a"), "w") as fh:
            fh.write(OWNER_FILE)
        code, out, err = self.go([])
        self.assertEqual(code, 0, err)
        self.assertEqual((self.puts, self.locks), ([], 0))
        with open(self.path_of("claude-a")) as fh:
            self.assertEqual(fh.read(), OWNER_FILE)
        self.assertIn("claude-a: ok; would update settings/accounts/claude-a.json", out)
        self.assertNotIn(self.store, out, "the store's location is not printed")
        self.assertIn("claude-b: ok; would create", out)
        self.assertIn('"time_utc": "12:00"', out)
        for t in (TOKEN_A, TOKEN_B):
            self.assertNotIn(t, out + err)

    def test_write_sets_only_observed_in_the_owners_file_and_creates_the_missing_one(self):
        with open(self.path_of("claude-a"), "w") as fh:
            fh.write(OWNER_FILE)
        code, out, err = self.go(["--write"])
        self.assertEqual(code, 0, err)
        self.assertEqual((len(self.puts), self.locks), (1, 2), "one lock to read the templates, one to write")
        self.assertEqual(self.heads, ["head-at-read"], "the write names the head the files were read at")
        self.assertEqual(self.token_reads_under_lock, [True], "the templates are read inside the lock, on the remote's head")
        a = self.puts[0]["accounts/claude-a.json"]
        self.assertTrue(a.startswith(OWNER_FILE[:OWNER_FILE.index("\n}")] + ","), "the owner's text is untouched up to the new key")
        got = json.loads(a)
        owner = json.loads(OWNER_FILE)
        self.assertEqual({k: v for k, v in got.items() if k != "observed"}, owner)
        obs = got["observed"]
        self.assertEqual(obs["read_at"], "2026-09-24T20:00:00.000Z")
        self.assertEqual(obs["weekly_reset"], {"weekday": "thursday", "time_utc": "12:00"})
        self.assertEqual((obs["organization_id"], obs["workspace_id"], obs["overage"]["disabled_reason"]), ("org-1", "ws-1", "out_of_credits"))
        self.assertEqual(obs["seven_day"], {"utilization": 76, "resets_at": "2026-10-01T12:00:00.000Z", "status": "allowed_warning"})
        self.assertNotIn("organization_type", obs, "no sign-in, no sign-in facts")
        self.assertEqual(list(json.loads(self.puts[0]["accounts/claude-b.json"])), ["account", "observed"])
        self.assertEqual(json.loads(self.puts[0]["accounts/claude-b.json"])["account"], "claude-b")
        self.assertIn("committed abc1234", out)
        for t in (TOKEN_A, TOKEN_B):
            self.assertNotIn(t, out + err + a)

    def test_a_failed_read_sets_status_and_error_and_no_figures(self):
        code, out, _ = self.go(["--write"], probe=lambda t: {"status": "read-failed", "http": 403})
        self.assertEqual(code, 1, "a failed read is not a clean run")
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual(o["status"], "read-failed")
        self.assertIn("HTTP 403", o["error"])
        self.assertEqual(set(o), {"read_at", "status", "error"}, "no zeros, no utilization, no reset")

    def test_a_template_without_a_token_says_no_token(self):
        code, _, _ = self.go(["--write"], tokens={"claude-a": None})
        self.assertEqual(code, 1)
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual(o["status"], "no-token")

    def test_a_sign_in_adds_the_plan_and_the_per_model_meter_only_then(self):
        self.sign_in(self.home, "claude-a")
        seen = []

        def read_signin(d, home=None):
            seen.append(os.path.basename(d))
            return {"status": "ok", "limits": [{"kind": "session", "percent": 11, "resets_at": "x"},
                                               {"kind": "weekly_scoped", "percent": 86, "resets_at": "2026-10-01T11:59:59Z", "model": "Fable"}]}
        self.go(["--write"], read_signin=read_signin)
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual(seen, ["claude-a"], "only the slug with a sign-in is read through it")
        self.assertEqual((o["organization_type"], o["rate_limit_tier"], o["billing_type"], o["extra_usage_enabled"]),
                         ("claude_max", "default_claude_max_20x", "stripe_subscription", False))
        self.assertEqual(o["subscription_created_at"], "2025-03-17T09:00:00Z")
        self.assertEqual(o["model_weekly"], [{"model": "Fable", "percent": 86, "resets_at": "2026-10-01T11:59:59Z"}])
        self.assertNotIn("who@example.org", json.dumps(o), "the e-mail is not copied")
        b = json.loads(self.puts[0]["accounts/claude-b.json"])["observed"]
        self.assertNotIn("model_weekly", b)

    def test_a_lone_surrogate_in_a_sign_in_string_is_unknown_not_a_failed_run(self):
        self.sign_in(self.home, "claude-a")
        f = os.path.join(U.accounts_dir(self.home, {}), "claude-a", ".claude.json")
        with open(f, "w", encoding="ascii") as fh:
            fh.write('{"oauthAccount": {"organizationType": "\\ud800", "billingType": "stripe_subscription"}}')
        self.go(["--write"], read_signin=lambda d, home=None: {"status": "ok", "limits": []})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertIsNone(o["organization_type"])
        self.assertEqual(o["billing_type"], "stripe_subscription")

    def test_a_lone_surrogate_in_the_harness_output_does_not_fail_the_write(self):
        self.sign_in(self.home, "claude-a")
        self.go(["--write"], read_signin=lambda d, home=None: {"status": "ok", "limits": [
            {"kind": "weekly_scoped", "percent": 1, "resets_at": None, "model": "Fa\ud800ble"}]})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertIsNone(o["model_weekly"][0]["model"], "malformed is unknown, not a made-up name")

    def test_a_store_that_moved_between_the_read_and_the_write_writes_nothing(self):
        calls = []

        def probe_then_move(tok):
            self.head_now = "a-newer-head"   # the remote moved while the accounts were being probed
            calls.append(tok)
            return probe_ok(tok)
        code, _, err = self.go(["--write"], probe=probe_then_move)
        self.assertEqual((code, self.puts), (1, []))
        self.assertIn("the store moved while the accounts were being read", err)
        self.assertNotIn("a commit may be made", err, "…and one that says nothing was written does not")

    def test_a_fragment_of_a_token_in_a_header_value_is_dropped_not_recorded(self):
        def echo(tok):
            return {**probe_ok(tok), "organization_id": TOKEN_A[:24]}
        code, out, err = self.go([], probe=echo)
        self.assertNotIn(TOKEN_A[:12], out + err)
        for piece in (TOKEN_A[-11:], TOKEN_A[3:14], TOKEN_A[10:18]):
            _, out, _ = self.go([], probe=lambda tok, p=piece: {**probe_ok(tok), "organization_id": p})
            self.assertNotIn(piece, out, "a whole value of 8 or more characters inside a token")
        self.assertIn("[token]", out)
        code, _, _ = self.go(["--write"], probe=echo)
        self.assertNotIn(TOKEN_A[:12], json.dumps(self.puts))

    def test_a_fifo_where_the_account_file_should_be_is_refused_promptly(self):
        os.mkfifo(self.path_of("claude-a"))
        code, out, _ = self.go(["--write"])
        self.assertEqual(code, 1)
        self.assertIn("claude-a: ok; refused: not a plain file", out)
        self.assertEqual(list(self.puts[0]), ["accounts/claude-b.json"])

    def test_malformed_sign_in_facts_are_null_and_a_link_is_no_sign_in(self):
        self.sign_in(self.home, "claude-a")
        f = os.path.join(U.accounts_dir(self.home, {}), "claude-a", ".claude.json")
        with open(f, "w") as fh:
            json.dump({"oauthAccount": {"subscriptionCreatedAt": "not-a-date", "organizationType": "a b\nc", "billingType": "stripe_subscription"}}, fh)
        self.go(["--write"], read_signin=lambda d, home=None: {"status": "ok", "limits": []})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual((o["subscription_created_at"], o["organization_type"], o["billing_type"]), (None, None, "stripe_subscription"))
        # claude-b is a link to claude-a's directory: it must not record claude-a's facts
        acc = U.accounts_dir(self.home, {})
        os.symlink(os.path.join(acc, "claude-a"), os.path.join(acc, "claude-b"))
        seen = []
        self.puts.clear()
        self.go(["--write"], read_signin=lambda d, home=None: (seen.append(os.path.basename(d)), {"status": "ok", "limits": []})[1])
        b = json.loads(self.puts[0]["accounts/claude-b.json"])["observed"]
        self.assertNotIn("billing_type", b)
        self.assertEqual(seen, ["claude-a"])

    def test_a_fifo_for_the_sign_in_profile_does_not_hang_the_read(self):
        self.sign_in(self.home, "claude-a")
        f = os.path.join(U.accounts_dir(self.home, {}), "claude-a", ".claude.json")
        os.unlink(f)
        os.mkfifo(f)
        self.go(["--write"], read_signin=lambda d, home=None: {"status": "ok", "limits": []})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertIsNone(o["billing_type"])

    def test_a_failed_probe_carries_no_sign_in_figures_even_when_the_sign_in_reads(self):
        self.sign_in(self.home, "claude-a")
        self.go(["--write"], probe=lambda t: {"status": "read-failed"},
                read_signin=lambda d, home=None: {"status": "ok", "limits": [{"kind": "weekly_scoped", "percent": 5, "resets_at": None, "model": "M"}]})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual(set(o), {"read_at", "status", "error"})

    def test_malformed_meters_from_the_sign_in_are_null_and_do_not_stop_the_write(self):
        self.sign_in(self.home, "claude-a")
        code, _, err = self.go(["--write"], read_signin=lambda d, home=None: {"status": "ok", "limits": [
            {"kind": "weekly_scoped", "percent": float("inf"), "resets_at": {"x": 1}, "model": "A"},
            {"kind": "weekly_scoped", "percent": 7, "resets_at": "not a date", "model": "B"},
            {"kind": "weekly_scoped", "percent": True, "resets_at": "2026-10-01T12:00:00Z", "model": "C"}]})
        self.assertEqual(code, 0, err)
        m = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]["model_weekly"]
        self.assertEqual([(x["percent"], x["resets_at"]) for x in m], [(None, None), (7, None), (None, "2026-10-01T12:00:00Z")])

    def test_a_sign_in_that_does_not_read_is_named_not_zeroed_and_its_free_text_is_never_kept(self):
        self.sign_in(self.home, "claude-a")
        code, out, err = self.go(["--write"], read_signin=lambda d, home=None: {"status": "failed", "error": ("x" * 190) + TOKEN_B[:12]})
        o = json.loads(self.puts[0]["accounts/claude-a.json"])["observed"]
        self.assertEqual(code, 1, "a sign-in that did not read is a lost read")
        self.assertIn("claude-a: ok; sign-in failed; created", out)
        self.assertEqual(o["signin"], {"status": "failed", "error": "the sign-in's /usage read did not give a report"})
        self.assertNotIn(TOKEN_B[:12], json.dumps(self.puts) + out + err, "not even the front of a token cut by the harness's 200 characters")
        self.assertNotIn("model_weekly", o)
        self.assertEqual(o["status"], "ok", "the probe's reading stands")
        self.assertNotIn(TOKEN_B, json.dumps(self.puts) + out + err)

    def test_a_file_that_is_not_json_is_refused_by_name_and_the_others_are_still_written(self):
        with open(self.path_of("claude-a"), "w") as fh:
            fh.write("plan: Max\n")
        code, out, _ = self.go(["--write"])
        self.assertEqual(code, 1)
        self.assertIn("claude-a: ok; refused: not a JSON object", out)
        self.assertEqual(list(self.puts[0]), ["accounts/claude-b.json"])
        with open(self.path_of("claude-a")) as fh:
            self.assertEqual(fh.read(), "plan: Max\n")

    def test_a_store_that_refuses_writes_nothing_and_says_so_without_a_token(self):
        def refuse(tree, expect_head=None):
            raise RuntimeError(f"the store said no about {TOKEN_A}")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = O.main(["--write"], home=self.home, env={}, tokens=lambda: {"claude-a": TOKEN_A}, path_of=self.path_of, put=refuse,
                          locked=self.locked, probe=probe_ok, read_signin=lambda d, home=None: {}, now=lambda: NOW,
                          say=lambda m: print(m, file=sys.stderr))
        self.assertEqual(code, 1)
        self.assertIn("the store refused or failed", err.getvalue())
        self.assertIn("(a commit may be made but not pushed)", err.getvalue(), "a refusal that does not say nothing was written carries the hedge")
        self.assertNotIn(TOKEN_A, out.getvalue() + err.getvalue())

    def test_usage_and_empty_store(self):
        self.assertEqual(self.go(["--bogus"])[0], 2)
        self.assertEqual(self.go([], tokens={})[0], 1)

    def test_fabric_accounts_dispatches_observe(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = A.main(["observe", "--nope"], home=self.home, env={})
        self.assertEqual((code, O.USAGE in err.getvalue()), (2, True))


if __name__ == "__main__":
    unittest.main()
