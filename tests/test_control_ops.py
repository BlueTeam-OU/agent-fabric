#!/usr/bin/env python3
"""The control agent's extractors (tools/fabric/control/ops), against a
scratch home: every section says what it knows or why not, and no output
ever carries a secret value. A port of the first half of
runtime/control/tests/ops.test.mjs, case for case; host, disk, accounts and
presence are tests/test_control_ops_machine.py's. The fakes have the shape
of the Python ops' injection points (a `run` called as subprocess.run is, a
`fetch` answering a Response), not the Node's exec."""
from __future__ import annotations

import base64
import http.client
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ops  # noqa: E402
import control.ops.keys  # noqa: E402,F401 — the package re-exports functions of the same names, so the modules come from sys.modules
import control.ops.usage  # noqa: E402,F401
from control.ops import util  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

keys_mod, usage_mod = sys.modules["control.ops.keys"], sys.modules["control.ops.usage"]

# A fence for any presence() a test forgets to give a hold: never the runner's own cache.
_HOLD = tempfile.TemporaryDirectory(prefix="ops-hold-")
os.environ["AGENT_FABRIC_HOLD_DIR"] = _HOLD.name

FIXTURE_ENV = {"OPENROUTER_API_KEY": "fixture-or-0123456789abcdefghij", "GH_TOKEN": "fixture-gh-ABCDEFGHIJ0123456789",
           "CLAUDE_BRIDGE_AUTH_TOKEN": "fixture-bridge-1234567890"}
ACCESS = "oauth-access-token-value-XYZ"
WHO = {"agent": "db-admin", "host": "develop-qzapp", "role": "db-admin", "project": "gzapp", "working_copy": "/home/db-admin/projects/gzapp"}
DAY = 86400000


# Fingerprints are literals (sha256sum of the fixture, first twelve digits), never computed by the code under test
# or by hashlib here: a change to what util.sha12 hashes then fails the tests that expect it.
TEMPLATE_FP = "752845b14925"
OPENROUTER_FP = "eb9c6584ec5e"


def iso(ms: float) -> str:
    return util.iso_ms(ms)


def write(path: str, text: str = "", mode: str = "w") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(text)
    return path


def touch(path: str, ms: float) -> None:
    os.utime(path, (ms / 1000, ms / 1000))


class Base(unittest.TestCase):
    def scratch(self, prefix: str = "ops-") -> str:
        t = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(t.cleanup)
        return t.name

    def home(self) -> str:
        h = self.scratch("ctl-home-")
        write(os.path.join(h, ".config", "agent-fabric", "secrets.env"), "".join(f"export {k}='{v}'\n" for k, v in FIXTURE_ENV.items()))
        write(os.path.join(h, ".claude", ".credentials.json"), json.dumps({"claudeAiOauth": {"accessToken": ACCESS, "refreshToken": "refresh-XYZ", "subscriptionType": "max"}}))
        write(os.path.join(h, ".claude.json"), json.dumps({"oauthAccount": {"emailAddress": "someone@example.org", "organizationName": "Example Org", "accountUuid": "u-1"}}))
        return h

    def assert_no_secret(self, obj) -> None:
        s = json.dumps(obj)
        for v in (*FIXTURE_ENV.values(), ACCESS, "refresh-XYZ"):
            self.assertNotIn(v, s, f"a secret value leaked into the output: {v[:6]}…")


def done(out: str = "", err: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, err)


class Fingerprint(unittest.TestCase):
    def test_a_fingerprint_is_twelve_hex_of_sha256(self):
        self.assertEqual(util.sha12("abc"), "ba7816bf8f01", "the first twelve digits of the published SHA-256 of 'abc'")
        self.assertEqual(util.sha12("sk-ant-oat01-TEMPLATE-TOKEN-VALUE"), TEMPLATE_FP)
        self.assertEqual(util.sha12(" Ab é-0123456789abcdef "), "a3fafcbf4e06", "mixed case, whitespace, non-ASCII and longer than 16: none of it is changed before the hash")


class Identity(Base):
    def test_the_account_and_the_claude_account_it_is_signed_into_no_secret(self):
        h = self.home()
        i = ops.identity(h, WHO)
        self.assertEqual(i, {**WHO, "claude_account": {"email": "someone@example.org", "organization": "Example Org"}, "credentials_present": True})
        self.assertEqual(list(i), ["agent", "host", "role", "project", "working_copy", "claude_account", "credentials_present"], "key order is the wire's")
        self.assert_no_secret(i)
        os.unlink(os.path.join(h, ".claude.json"))
        self.assertIsNone(ops.identity(h, WHO)["claude_account"], "no profile record: null, not a throw")

    def test_a_login_on_a_template_is_named_by_the_tokens_fingerprint_and_usage_comes_from_headers(self):
        h = self.home()
        template = "sk-ant-oat01-TEMPLATE-TOKEN-VALUE"
        write(os.path.join(h, ".config", "agent-fabric", "secrets.env"), f"export CLAUDE_CODE_OAUTH_TOKEN='{template}'\n", "a")
        i = ops.identity(h, WHO)
        self.assertEqual(i["claude_account"], {"via": "setup-token", "token_sha256_12": TEMPLATE_FP, "email": None, "organization": None})
        self.assertEqual(i["own_sign_in"], {"email": "someone@example.org", "organization": "Example Org"}, "the own sign-in is still said, as what it is")
        self.assertEqual(list(i)[-2:], ["own_sign_in", "credentials_present"])
        hd = {"anthropic-ratelimit-unified-5h-utilization": "0.08", "anthropic-ratelimit-unified-5h-reset": "1791449400", "anthropic-ratelimit-unified-5h-status": "allowed",
              "anthropic-ratelimit-unified-7d-utilization": "0.78", "anthropic-ratelimit-unified-7d-reset": "1791460800", "anthropic-ratelimit-unified-7d-status": "allowed_warning"}
        seen: list = []

        def reply(status, headers):
            def fetch(url, method="GET", headers_=None, body=None, timeout=None, **kw):
                seen.append((url, kw.get("headers", headers_) or {}, json.loads(body)))
                return usage_mod.Response(status, headers)
            return fetch
        u = ops.usage(h, fetch=reply(200, hd), url="https://usage.invalid", messages_url="https://messages.invalid")
        self.assertEqual(u, {"status": "ok", "via": "setup-token", "subscription": None,
                             "five_hour": {"utilization": 8, "resets_at": "2026-10-08T08:50:00.000Z", "status": "allowed"},
                             "seven_day": {"utilization": 78, "resets_at": "2026-10-08T12:00:00.000Z", "status": "allowed_warning"}})
        self.assertEqual([(x[0], x[1]["Authorization"], x[2]["max_tokens"]) for x in seen], [("https://messages.invalid", f"Bearer {template}", 1)],
                         "one inference call with the template token, one output token; the old sign-in's windows are another account's")
        self.assertEqual(ops.usage(h, fetch=reply(429, hd), url="u", messages_url="m")["seven_day"]["utilization"], 78, "a full window answers 429 and is still a reading")
        self.assertEqual(ops.usage(h, fetch=reply(401, {}), url="u", messages_url="m"), {"status": "read-failed", "via": "setup-token", "http": 401})

        def refused(*_a, **_k):
            raise ConnectionRefusedError("ECONNREFUSED")
        self.assertEqual(ops.usage(h, fetch=refused, url="u", messages_url="m"), {"status": "read-failed", "via": "setup-token"})
        self.assertNotIn(template, json.dumps(u), "the template token leaked into the reading")
        self.assertEqual([k for k in ops.keys(h) if k["name"] == "CLAUDE_CODE_OAUTH_TOKEN"], [{"name": "CLAUDE_CODE_OAUTH_TOKEN", "present": True, "sha256_12": TEMPLATE_FP}])
        self.assertNotIn(template, json.dumps([i, ops.keys(h)]))
        self.assert_no_secret(i)


class Usage(Base):
    def test_the_two_windows_through_the_accounts_own_token_in_one_header_and_nowhere_else(self):
        h = self.home()
        seen: list = []
        body = json.dumps({"five_hour": {"utilization": 12.5, "resets_at": "2026-09-17T10:00:00+00:00"}, "seven_day": {"utilization": 80, "resets_at": "2026-09-21T16:00:00+00:00"}}).encode()

        def fetch_ok(url, headers=None, **kw):
            seen.append((url, headers))
            return usage_mod.Response(200, {}, body)
        u = ops.usage(h, fetch=fetch_ok)
        self.assertEqual(u, {"status": "ok", "five_hour": {"utilization": 12.5, "resets_at": "2026-09-17T10:00:00+00:00"},
                             "seven_day": {"utilization": 80, "resets_at": "2026-09-21T16:00:00+00:00"}, "subscription": "max"})
        self.assertEqual((seen[0][1]["Authorization"], seen[0][1]["anthropic-beta"]), (f"Bearer {ACCESS}", "oauth-2025-04-20"))
        self.assert_no_secret(u)
        self.assertEqual(ops.usage(h, fetch=lambda *a, **k: usage_mod.Response(401)), {"status": "read-failed", "http": 401})
        inf = b'{"five_hour": {"utilization": Infinity, "resets_at": "x"}}'
        self.assertEqual(ops.usage(h, fetch=lambda *a, **k: usage_mod.Response(200, {}, inf)), {"status": "unreadable"}, "JSON.parse refuses Infinity")

        def torn(*_a, **_k):
            raise http.client.IncompleteRead(b"")
        self.assertEqual(ops.usage(h, fetch=torn), {"status": "read-failed"}, "a reply cut short is no answer, not a failed section")

        def refused(*_a, **_k):
            raise ConnectionRefusedError("ECONNREFUSED")
        self.assertEqual(ops.usage(h, fetch=refused), {"status": "read-failed"})
        self.assertEqual(ops.usage(h, fetch=lambda *a, **k: usage_mod.Response(200, {}, b"{bad")), {"status": "unreadable"})
        os.unlink(os.path.join(h, ".claude", ".credentials.json"))
        self.assertEqual(ops.usage(h, fetch=fetch_ok), {"status": "no-credentials"})

    def test_a_reply_never_quotes_the_token_in_an_error(self):
        h = self.home()

        def bad_header(*_a, **_k):
            raise ValueError(f"Invalid header value 'Bearer {ACCESS}'")
        self.assertEqual(ops.usage(h, fetch=bad_header), {"status": "read-failed"})


class SigningAndKeys(Base):
    def test_signing_key_secret_asks_the_key_git_signs_with_a_usable_signing_key_never_a_count(self):
        asked: list[str] = []
        key = "ABCDEF0123456789"
        usable = f"sec:u:255:22:{key}:1:::::::scSC:::+:::23::0:\nssb:u:255:22:0448AC70CD742422:1::::::s:::+:::23:\n"
        stub = f"sec:u:255:22:{key}:1:::::::cC:::#:::23::0:\nssb:u:255:22:0448AC70CD742422:1::::::s:::#:::23:\n"

        def run(listing, k=key):
            def f(cmd, **kw):
                asked.append(" ".join(cmd))
                if cmd[0] == "git":
                    if not k:
                        raise subprocess.CalledProcessError(1, cmd)
                    return done(k + "\n")
                if cmd[0] == "gpg" and listing is not None:
                    return done(listing)
                raise subprocess.CalledProcessError(2, cmd)
            return f
        row = {"name": keys_mod.SIGNING_ROW}
        self.assertEqual(ops.signing_secret(run(usable)), {**row, "present": True})
        self.assertIn(f"gpg --list-secret-keys --with-colons -- {key}", asked)
        self.assertEqual(ops.signing_secret(run(None)), {**row, "present": False}, "the store key alone is not it")
        self.assertEqual(ops.signing_secret(run(stub)), {**row, "present": False}, "a stub cannot sign")
        self.assertEqual(ops.signing_secret(run(usable, "")), {**row, "present": False}, "no signing key configured")

    def test_keys_names_and_twelve_digit_fingerprints_never_a_value(self):
        h = self.home()
        k = ops.keys(h)
        self.assertEqual([x["name"] for x in k], ops.KEY_NAMES)
        orr = next(x for x in k if x["name"] == "OPENROUTER_API_KEY")
        self.assertEqual((orr["present"], orr["sha256_12"]), (True, OPENROUTER_FP))
        self.assertEqual(next(x for x in k if x["name"] == "OPENAI_API_KEY"), {"name": "OPENAI_API_KEY", "present": False})
        self.assert_no_secret(k)
        self.assertEqual([x["present"] for x in ops.keys("/nonexistent")], [False] * len(ops.KEY_NAMES))

    def test_store_refusal_no_store_no_base_verified_refused_unreadable_and_each_mirrors(self):
        home = self.scratch("store-home-")
        store, children = os.path.join(home, "store"), os.path.join(home, "children")
        row = lambda: ops.store_refusal(home, store, children)  # noqa: E731
        R = keys_mod.STORE_ROW
        cfg = os.path.join(store, ".git", "config")
        self.assertEqual(row(), {"name": R, "present": False, "state": "no store"}, "no .git: no store, never verified")
        write(cfg, "[core]\n\tbare = false\n")
        self.assertEqual(row(), {"name": R, "present": False, "state": "no base"}, "no trusted base: it verifies nothing")
        write(cfg, f"[core]\n\tbare = false\n[agent-fabric]\n\ttrustedbase = {'a' * 40}\n")
        self.assertEqual(row(), {"name": R, "present": True, "state": "verified"})
        write(cfg, f"[agent-fabric]\n\ttrustedbase = {'A' * 40}\n")
        self.assertEqual(row()["state"], "no base", "an uppercase base is none to the verifier, so none here")
        write(cfg, f"[agent-fabric]\n\tTrustedBase = {'a' * 40}\n\ttrustedbase = x\n")
        self.assertEqual(row()["state"], "no base", "git reads the last value: a good line before a bad one is no base")
        write(cfg, f"[agent-fabric]\n\ttrustedbase = x\n\tTRUSTEDBASE = {'a' * 40}\n")
        self.assertEqual(row()["state"], "verified", "…and a good last line, the key in any case, is the base")
        refusal = os.path.join(store, ".git", "agent-fabric-refusal.json")
        write(refusal, json.dumps({"commit": "0123456789abcdef0123", "reason": "not signed", "at": "2026-10-04T10:00:00Z"}))
        self.assertEqual(row(), {"name": R, "present": False, "state": "refused", "refused": {"commit": "0123456789ab", "at": "2026-10-04T10:00:00Z", "reason": "not signed"}})
        write(refusal, "not json")
        self.assertEqual(row()["state"], "unreadable", "a record that cannot be read is no clean bill")
        os.unlink(refusal)
        kid = "01a106ee-84ec-74bc-84ef-3720a55d6a3f"
        os.makedirs(os.path.join(children, kid, ".git"))
        self.assertEqual(row()["mirrors"], [{"agent_id": kid, "state": "unreadable"}], "a mirror whose config cannot be read is said (review of #94)")
        write(os.path.join(children, kid, ".git", "config"), "[core]\n\tbare = false\n")
        self.assertEqual(row(), {"name": R, "present": False, "state": "verified", "mirrors": [{"agent_id": kid, "state": "no base"}]},
                         "a mirror with no base refuses every verified operation: not clean, said by name")
        write(os.path.join(children, kid, ".git", "config"), f"[agent-fabric]\n\ttrustedbase = {'b' * 40}\n")
        write(os.path.join(children, "not-an-id", ".git", "agent-fabric-refusal.json"), "{}")
        self.assertEqual(row(), {"name": R, "present": True, "state": "verified"}, "a clean mirror adds nothing; a name that is no agent id is no mirror")
        write(os.path.join(children, kid, ".git", "agent-fabric-refusal.json"), json.dumps({"commit": "ffff", "reason": "outsider", "at": "T"}))
        self.assertEqual(row(), {"name": R, "present": False, "state": "verified", "mirrors": [{"agent_id": kid, "commit": "ffff", "at": "T", "reason": "outsider"}]},
                         "the own store verified, a mirror refused: not clean")
        import shutil
        shutil.rmtree(os.path.join(children, kid))
        self.assertEqual(row(), {"name": R, "present": True, "state": "verified"}, "control: no mirror and no record, nothing said")
        write(os.path.join(children, f"{kid}.refusal.json"), json.dumps({"commit": "eeee", "reason": "not signed", "at": "U"}))
        self.assertEqual(row(), {"name": R, "present": False, "state": "verified", "mirrors": [{"agent_id": kid, "commit": "eeee", "at": "U", "reason": "not signed"}]},
                         "a removed mirror's kept refusal is said by name")


class FabricAndSession(Base):
    def test_fabric_head_branch_behind_dirty_through_a_fake_git_a_failed_fetch_is_said(self):
        calls: list[str] = []

        def run(cmd, **kw):
            a = " ".join(cmd[3:])
            calls.append(a)
            self.assertTrue(kw["timeout"] and kw["check"], "every git call is bounded and checked")
            if a.startswith("rev-parse --short"):
                return done("abc1234\n")
            if a.startswith("rev-parse --abbrev-ref"):
                return done("main\n")
            if a.startswith("status"):
                return done("")
            if a.startswith("fetch"):
                raise subprocess.CalledProcessError(128, cmd)
            if a.startswith("rev-list"):
                return done("3\n")
            return done("")
        self.assertEqual(ops.fabric("/some/root", run), {"status": "ok", "root": "/some/root", "head": "abc1234", "branch": "main", "dirty": False, "fetch": "failed", "behind": 3})

        def not_git(cmd, **kw):
            raise subprocess.CalledProcessError(128, cmd)
        self.assertEqual(ops.fabric("/no/checkout", not_git)["status"], "not-a-checkout")

        def hung(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 10)
        self.assertEqual(ops.fabric("/no/checkout", hung)["status"], "not-a-checkout", "a hung git costs the section, not the daemon")

    def test_session_counts_the_harness_processes_of_the_uid_none_is_zero(self):
        def run(cmd, **kw):
            self.assertEqual(cmd[1:], ["-u", "4242", "-x", "claude"])
            return done("111\n222\n")
        s = ops.session(4242, run)
        self.assertEqual(s["claude_processes"], 2)
        self.assertIsInstance(s["planning"], bool)
        self.assertEqual(ops.session(4242, lambda cmd, **kw: done("", "", 1))["claude_processes"], 0)

        def gone(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        self.assertEqual(ops.session(4242, gone)["claude_processes"], 0)


class Script(Base):
    def test_letters_by_script_thinking_and_text_apart_nothing_of_the_text_leaves(self):
        self.assertEqual(ops.script_counts("Hello, world! 123"), {"latin": 10})
        self.assertEqual(ops.script_counts("გამარჯობა hello"), {"georgian": 9, "latin": 5})
        self.assertEqual(ops.script_counts("привет"), {"cyrillic": 6})
        h = self.scratch("script-home-")
        d = os.path.join(h, ".claude", "projects", "-home-x-projects-demo")

        def turn(thinking, text):
            return json.dumps({"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": thinking}, {"type": "text", "text": text}]}}, ensure_ascii=False)
        live = os.path.join(d, "live.jsonl")
        lines = [turn("I think in English about this", "გამარჯობა — the answer in Georgian, then its rendering"), turn("ვფიქრობ ქართულად", "ok"),
                 json.dumps({"type": "user", "message": {"content": "ignored"}}), "not json"]
        write(live, "\n".join(lines) + "\n")
        old = write(os.path.join(d, "old.jsonl"), turn("ძველი", "old") + "\n")
        past = time.time() * 1000 - 48 * 3600000
        touch(old, past)
        s = ops.script(h)
        self.assertEqual((s["status"], s["files"], s["turns"]), ("ok", 1, 2), "a record older than the window is not read")
        self.assertEqual(s["thinking"]["letters"], 24 + 15)
        self.assertGreater(s["thinking"]["latin"], s["thinking"]["georgian"], s)
        self.assertTrue(s["text"]["georgian"] > 0 and s["text"]["latin"] > 0)
        self.assertEqual(s["thinking_blocks"], {"only": 0, "mixed": 0, "latin": 1, "empty": 1}, "the English block is latin; the short Georgian one is under the 20-letter floor")
        write(live, turn("ვფიქრობ ქართულად და ვწერ ქართულად, ეს ბლოკი მხოლოდ ქართულია", "x") + "\n" + turn("ნახევარი ქართული ნახევარი and half of it English text", "x") + "\n", "a")
        self.assertEqual(ops.script(h)["thinking_blocks"], {"only": 1, "mixed": 1, "latin": 1, "empty": 1})
        self.assertNotIn("answer", json.dumps(s), "no text leaves, only counts")
        self.assertEqual(ops.script(h, hours=72)["files"], 2)
        self.assertEqual(ops.script("/nonexistent")["status"], "no-records")
        # The notes: the signature the holder controls, one file a day in the locale, paragraphs binned.
        self.assertEqual(s["notes"]["status"], "none")
        nd = os.path.join(h, "state", "agent-fabric", "agents", "ge", "notes")
        write(os.path.join(nd, "2026-09-17.md"), "მოთხოვნა: გადათარგმნილი მოთხოვნა ქართულად, სრული აბზაცი.\n\nჩემი მსჯელობა ქართულად: ეს ტექსტი მხოლოდ ქართულია და საკმაოდ გრძელი.\n\nA paragraph written in English, long enough to count as a block here.\n")

        def fake_lang(paras, **_kw):
            return {"status": "ok", "paragraphs": len(paras), "unreliable": 0, "shares": {"ka": 100}, "dominant": {"ka": len(paras)}}
        self.assertEqual(ops.script(h, notes=nd)["notes"]["language"]["status"], "unavailable", "no venv on this scratch home: said, not guessed")
        with_notes = ops.script(h, notes=nd, langid=fake_lang)
        self.assertEqual(with_notes["notes"]["language"], {"status": "ok", "paragraphs": 3, "unreliable": 0, "shares": {"ka": 100}, "dominant": {"ka": 3}}, "every note paragraph reaches the detector")
        self.assertEqual((with_notes["notes"]["status"], with_notes["notes"]["files"]), ("ok", 1))

        def never(_p, **_kw):
            raise AssertionError("the source locale's notes are not measured")
        src = ops.script(h, notes=nd, langid=never, source=True)
        self.assertEqual(src["notes"], {"status": "not measured", "reason": "the source locale"})
        self.assertEqual(src["thinking"], with_notes["thinking"], "the transcript is measured as for any holder")
        self.assertEqual(with_notes["notes"]["blocks"], {"only": 2, "mixed": 0, "latin": 1, "empty": 0}, with_notes["notes"])
        self.assertGreater(with_notes["notes"]["georgian"], with_notes["notes"]["latin"])
        self.assertNotIn("მოთხოვნა", json.dumps(with_notes, ensure_ascii=False), "no note text leaves")
        self.assertEqual(ops.notes_dir("/h", {"XDG_STATE_HOME": "/st"}, "ge"), "/st/agent-fabric/agents/ge/notes")
        self.assertEqual(ops.notes_dir("/h", {}, "ge"), "/h/.local/state/agent-fabric/agents/ge/notes")
        # The workers: the subagent transcripts beside the session whose sidecar names the locale worker; its USER records the input.
        self.assertEqual(s["workers"], {"status": "none", "other_subagents": 0})
        sub = os.path.join(d, "live", "subagents")

        def user(c):
            return json.dumps({"type": "user", "message": {"role": "user", "content": c}}, ensure_ascii=False)

        def meta(name, agent_type):
            write(os.path.join(sub, f"{name}.meta.json"), json.dumps({"agentType": agent_type, "model": "opus"}))
        handback = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "SubagentHandback", "input": {}}]}})
        worker = [user("თხოვნა: გადახედე ამ ტექსტს და უპასუხე ქართულად, სრული აბზაცი აქ."),
                  turn("", "პასუხი ქართულად, საკმაოდ გრძელი აბზაცი რომ დაითვალოს ბლოკად."),
                  user([{"type": "text", "text": "მეორე თხოვნა ქართულად, ისევ საკმაოდ გრძელი აბზაცი, სამოცამდე ასო."}]),
                  user("<system-reminder>\nYour final report is delivered through SubagentHandback; a plain final message is NOT delivered. Call it now.\n</system-reminder>"),
                  json.dumps({"type": "attachment", "attachment": {"type": "x"}}),
                  turn("", "მეორე პასუხი ქართულად, საკმაოდ გრძელი ტექსტი აქაც."), handback]
        write(os.path.join(sub, "agent-aaa.jsonl"), "\n".join(worker) + "\n")
        meta("agent-aaa", "locale-worker")
        reviewer = [user("Repository: /x. Review the range a..b"), json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "Read", "input": {}}]}}), turn("", "Findings: none."), handback]
        write(os.path.join(sub, "agent-bbb.jsonl"), "\n".join(reviewer) + "\n")
        meta("agent-bbb", "code-review")
        write(os.path.join(sub, "agent-nometa.jsonl"), user("a subagent with no sidecar, long enough to be a block") + "\n")
        w = ops.script(h, langid=fake_lang)["workers"]
        self.assertEqual((w["input"]["language"]["paragraphs"], w["text"]["language"]["paragraphs"]), (2, 2))
        self.assertEqual((w["status"], w["files"], w["other_subagents"], w["turns"]), ("ok", 1, 2, 3), "only the sidecar that says locale-worker")
        self.assertEqual(w["tool_uses"], 0, "the hand-back is not a tool use of the worker")
        self.assertEqual(w["input"]["blocks"], {"only": 2, "mixed": 0, "latin": 0, "empty": 0}, f"the injected reminder is not the bridge's input: {w['input']}")
        self.assertEqual(w["text"]["blocks"], {"only": 2, "mixed": 0, "latin": 0, "empty": 0})
        self.assertEqual(w["input"]["georgian"], 100)
        self.assertGreater(w["input"]["letters"], 0)
        self.assertNotIn("თხოვნა", json.dumps(w, ensure_ascii=False), "no worker text leaves")
        write(os.path.join(sub, "agent-aaa.jsonl"), user("A paragraph of English that the bridge let through to the worker.") + "\n"
              + json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u", "name": "TaskStop", "input": {}}]}}) + "\n"
              + turn("", "მოკლე პასუხი ქართულად, საკმაოდ გრძელი რომ ბლოკი გამოვიდეს.") + "\n", "a")
        leak = ops.script(h)["workers"]
        self.assertEqual(leak["input"]["blocks"], {"only": 2, "mixed": 0, "latin": 1, "empty": 0}, "the leak is one latin input block")
        self.assertEqual(leak["text"]["blocks"], {"only": 3, "mixed": 0, "latin": 0, "empty": 0}, "the answers stay Georgian")
        self.assertEqual(leak["tool_uses"], 1)
        stale = write(os.path.join(sub, "agent-ccc.jsonl"), user("old English input, long enough to be a block") + "\n")
        meta("agent-ccc", "locale-worker")
        touch(stale, past)
        self.assertEqual(ops.script(h)["workers"]["files"], 1, "a worker transcript older than the window is not read")
        self.assertEqual(ops.worker_transcripts(["/nonexistent/s.jsonl"]), {"status": "none", "other_subagents": 0})

    def test_source_locale_a_language_culture_holder_whose_locale_json_carries_the_source_tag(self):
        root = self.scratch("src-locale-")

        def put(suffix, body):
            write(os.path.join(root, "identities", "roles", "language-culture", "locale", suffix, "locale.json"), body)
        put("en", json.dumps({"tag": ops.activity.SOURCE_TAG}))
        put("ge", json.dumps({"tag": "ka-GE"}))
        put("xx", "{broken")
        put("zq", json.dumps({"tag": ops.activity.SOURCE_TAG}))  # a suffix no live locale has: the fixture, not the checkout, answers
        sl = lambda who, r=root: ops.source_locale(who, root=r)  # noqa: E731
        self.assertIs(sl({"role": "language-culture", "agent": "language-culture-en"}), True)
        self.assertIs(sl({"role": "language-culture", "agent": "language-culture-ge"}), False)
        self.assertIs(sl({"role": "python-dev", "agent": "language-culture-en"}), False, "the role bound, not the login name")
        self.assertIs(sl({"role": "language-culture", "agent": "language-culture-xx"}), False, "unreadable: measured, as before")
        self.assertIs(sl({"role": "language-culture", "agent": "language-culture-zz"}), False, "no locale")
        with open(os.path.join(HERE, "tools", "fabric", "lint_rules", "locales.py"), encoding="utf-8") as fh:
            self.assertRegex(fh.read(), rf'(?m)^SOURCE_TAG = "{ops.activity.SOURCE_TAG}"$')
        self.assertIs(sl({"role": "language-culture", "agent": "language-culture-zq"}), True, "a locale whose locale.json carries the source tag")

    def test_collect_script_asks_whether_its_holder_is_the_source_locale(self):
        home = self.scratch("src-home-")
        os.makedirs(os.path.join(home, ".claude", "projects"))
        root = self.scratch("src-root-")
        for suffix, tag in (("zq", ops.activity.SOURCE_TAG), ("ge", "ka-GE")):
            write(os.path.join(root, "identities", "roles", "language-culture", "locale", suffix, "locale.json"), json.dumps({"tag": tag}))

        def ask(who, h=home):
            return ops.collect("script", {"home": h, "who": who, "root": root})["script"]["notes"]
        en = {"role": "language-culture", "agent": "language-culture-zq"}
        self.assertEqual(ask(en), {"status": "not measured", "reason": "the source locale"})
        bare = self.scratch("src-bare-")
        none = ops.collect("script", {"home": bare, "who": en, "root": root})["script"]
        self.assertEqual(none["status"], "no-records")
        self.assertEqual(none["notes"], {"status": "not measured", "reason": "the source locale"})
        nd = os.path.join(bare, "notes")
        write(os.path.join(nd, "d.md"), "მოთხოვნა: გადათარგმნილი მოთხოვნა ქართულად, სრული აბზაცი.\n")
        other = ops.script(bare, notes=nd, langid=lambda p, **kw: {"status": "unavailable"})
        self.assertEqual(other["status"], "no-records")
        self.assertEqual(other["notes"]["status"], "ok", "any holder's notes, with or without transcripts")
        self.assertEqual(ask({"role": "language-culture", "agent": "language-culture-ge"})["status"], "none")


class Recall(Base):
    def test_the_corpus_reads_index_slice_search_identity_and_the_sessions_that_read_none_paths_only(self):
        h = self.scratch("recall-home-")
        d = os.path.join(h, ".claude", "projects", "-home-x-projects-demo")
        now = time.time() * 1000
        fresh, stale = iso(now), iso(now - 72 * 3600000)

        def use(name, inp, ts=fresh):
            return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})

        def say(text, ts=fresh):
            return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": text}]}})
        wc, fab = f"{h}/projects/demo", f"{h}/projects/agent-fabric"
        write(os.path.join(d, "one.jsonl"), "\n".join([
            say("hello"),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/INDEX.md"}),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/solution/auth.md"}),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/solution/auth.md"}),
            use("Read", {"file_path": f"{fab}/memory/domains/backend-dev/domain/idempotency.md"}),
            use("Grep", {"pattern": "outbox", "path": f"{fab}/memory/domains/backend-dev"}),
            use("Grep", {"pattern": f"outbox-pattern-only {wc}/.agent-fabric/memory/backend-dev"}),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/crossref.json"}),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/last-drain-report.json"}),
            use("Bash", {"command": f"sed -n 1,40p {wc}/.agent-fabric/memory/backend-dev/workflow.md"}),
            use("Read", {"file_path": f"{fab}/identities/roles/backend-dev/charter.md"}),
            use("Read", {"file_path": f"{wc}/src/main.rs"}),
            use("Read", {"file_path": ".agent-fabric/memory/backend-dev/INDEX.md"}),
            use("Read", {"file_path": "memory/domains/backend-dev/domain/idempotency.md"}),
            say("weeks ago", stale),
            use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/solution/auth.md"}, stale),
            "not json",
        ]) + "\n")
        write(os.path.join(d, "two.jsonl"), "\n".join([say("x"), use("Read", {"file_path": f"{wc}/README.md"})]) + "\n")
        write(os.path.join(d, "two", "subagents", "agent-1.jsonl"), use("Read", {"file_path": f"{fab}/memory/shared/domain-x.md"}) + "\n")
        old = write(os.path.join(d, "old.jsonl"), use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/INDEX.md"}) + "\n")
        touch(old, now - 48 * 3600000)

        r = ops.recall(h)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["sessions"], 3, "two sessions and one subagent record")
        self.assertEqual(r["turns"], 14 + 2 + 1, "the two stale records are outside the window")
        self.assertEqual({k: r[k] for k in ("index", "slice", "search", "identity")}, {"index": 2, "slice": 5, "search": 3, "identity": 1},
                         "relative paths count; the crossref and the drain report are not slices; a grep naming a corpus directory only in its pattern is a search; the stale read does not count")
        self.assertEqual(r["sessions_without_recall"], 1, "session two opened neither an index nor a slice")
        self.assertEqual(r["top"][0]["reads"], 2, "the stale third read of auth.md is not counted")
        self.assertRegex(r["top"][0]["path"], r"^~/projects/demo/.agent-fabric/memory/backend-dev/solution/auth\.md$", "the home is folded to ~")
        olddir = os.path.join(h, ".claude", "projects", "-home-x-projects-old")
        write(os.path.join(olddir, "resumed.jsonl"), "\n".join([say("x", stale), use("Read", {"file_path": f"{wc}/.agent-fabric/memory/backend-dev/INDEX.md"}, stale)]) + "\n")
        r2 = ops.recall(h)
        self.assertEqual((r2["sessions"], r2["index"]), (3, 2), "a file with no record in the window is not a session")
        self.assertNotIn("outbox", json.dumps(r), "a grep pattern is never reported: paths of reads and counts only")
        self.assertTrue("crossref" not in json.dumps(r) and "drain-report" not in json.dumps(r), "non-slice reads under the corpus are not in top")
        self.assertEqual(ops.recall(self.scratch("recall-empty-"))["status"], "no-records")
        k = ops.recall_kind
        self.assertEqual(k("Read", {"file_path": "/x/memory/domains/a/INDEX.md"})["kind"], "index")
        self.assertEqual(k("Read", {"file_path": "/x/memory/shared/domain-y.md"})["kind"], "slice")
        self.assertIsNone(k("Read", {"file_path": "/x/memory/README.md"}), "the corpus README is not a slice")
        self.assertIsNone(k("Read", {"file_path": "/x/memory/shared/README.md"}), "nor the shared README")
        self.assertIsNone(k("Read", {"file_path": "/x/.agent-fabric/memory/last-drain-report.json"}), "nor a drain report")
        self.assertIsNone(k("Edit", {"file_path": "/x/memory/domains/a/b.md"}), "a write is not a recall")
        self.assertIsNone(k("Bash", {"command": "ls"}))
        self.assertEqual(k("Read", {"file_path": ".agent-fabric/memory/db-admin/INDEX.md"})["kind"], "index", "a repository-relative index")
        self.assertEqual(k("Bash", {"command": "sed -n 1,20p memory/domains/db-admin/domain/x.md"})["kind"], "search", "a relative path in a command")
        self.assertIsNone(k("Read", {"file_path": "/x/some-memory/domains/a/b.md"}), "a directory merely ending in memory is not the corpus")


class Memory(Base):
    def test_memory_dirs_every_directory_with_a_memory_matched_to_its_working_copy_by_slug(self):
        h = self.scratch("mem-home-")
        wc = os.path.join(h, "projects", "gzapp")
        dotted = os.path.join(h, "projects", "gzapi.ge")
        for d in (wc, dotted, os.path.join(h, "projects", "agent-fabric")):
            os.makedirs(d)
        write(os.path.join(h, "projects", "notes.txt"), "not a working copy")
        slug = ops.memory_slug

        def mem(s):
            d = os.path.join(h, ".claude", "projects", s, "memory")
            os.makedirs(d, exist_ok=True)
            return d
        write(os.path.join(mem(slug(wc)), "fact.md"), "---\nname: fact\n---\nx")
        write(os.path.join(mem(slug(wc)), "MEMORY.md"), "- index")
        write(os.path.join(mem("-home-elsewhere-old-checkout"), "stray.md"), "x")
        write(os.path.join(mem(slug(dotted)), "brand.md"), "x")
        write(os.path.join(mem(slug(os.path.join(h, "projects", "agent-fabric"))), "MEMORY.md"), "- only the index")
        os.makedirs(os.path.join(h, ".claude", "projects", "-no-memory-dir"))
        base = os.path.join(h, ".claude", "projects")
        ds = sorted(ops.memory_dirs(h), key=lambda x: x["slug"])
        want = sorted([
            {"slug": "-home-elsewhere-old-checkout", "memory": os.path.join(base, "-home-elsewhere-old-checkout", "memory"), "files": 1, "working_copy": None},
            {"slug": slug(dotted), "memory": os.path.join(base, slug(dotted), "memory"), "files": 1, "working_copy": dotted},
            {"slug": slug(wc), "memory": os.path.join(base, slug(wc), "memory"), "files": 1, "working_copy": wc}], key=lambda x: x["slug"])
        self.assertEqual(ds, want)
        self.assertTrue(slug(dotted).endswith("-projects-gzapi-ge"), "the dotted copy is matched under the harness's spelling")
        self.assertEqual(ops.memory_dirs("/nonexistent"), [])
        os.makedirs(os.path.join(h, "projects", "gzapi-ge"))   # the same slug as gzapi.ge
        amb = next(d for d in ops.memory_dirs(h) if d["slug"] == slug(dotted))
        self.assertEqual((amb["working_copy"], amb.get("ambiguous")), (None, True), "two working copies with one slug: neither is guessed")
        self.assertEqual(slug("/home/x/projects/gzapp"), "-home-x-projects-gzapp")
        self.assertEqual(slug("/home/x/projects/gzapp.decks"), "-home-x-projects-gzapp-decks", "a dot is a dash too, as the harness names it")
        self.assertEqual(slug("/home/x/.claude-mem"), "-home-x--claude-mem")

    def test_memory_dirs_the_projects_roots_own_memory_is_filed_under_the_fabric_checkout_marked(self):
        h = self.scratch("mem-root-")
        projects = os.path.join(h, "projects")
        fabric = os.path.join(projects, "agent-fabric")
        os.makedirs(fabric)
        d = os.path.join(h, ".claude", "projects", ops.memory_slug(projects), "memory")
        write(os.path.join(d, "fact.md"), "---\nname: fact\n---\nx")
        self.assertEqual(ops.memory_dirs(h), [{"slug": ops.memory_slug(projects), "memory": d, "files": 1, "working_copy": fabric, "projects_root": True}])
        elsewhere = os.path.join(h, "checkouts", "fabric")
        os.makedirs(elsewhere)
        self.assertEqual(ops.memory_dirs(h, projects, elsewhere)[0]["working_copy"], elsewhere, "the checkout the op runs from, wherever it is")
        import shutil
        shutil.rmtree(fabric)
        self.assertEqual(ops.memory_dirs(h), [{"slug": ops.memory_slug(projects), "memory": d, "files": 1, "working_copy": None}], "no checkout: not guessed")

    def test_memory_the_projects_roots_store_is_harvested_as_its_own_the_checkouts_as_before(self):
        calls: list[list[str]] = []

        def run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, b"x", b"{}")
        dirs = [{"slug": "s-root", "memory": "/m/root", "files": 1, "working_copy": "/h/projects/agent-fabric", "projects_root": True},
                {"slug": "s-fab", "memory": "/m/fab", "files": 1, "working_copy": "/h/projects/agent-fabric"}]
        m = ops.memory("/h", root="/r", run=run, dirs=dirs)
        self.assertIs(m["bundles"][0]["projects_root"], True)
        i = calls[0].index("--store")
        self.assertEqual(calls[0][i:i + 2], ["--store", "projects-root"])
        self.assertNotIn("--store", calls[1], "the checkout's own store keeps its key")

    def test_memory_one_harvester_run_per_directory_gzipped_base64_in_parts_a_failure_and_a_stray_are_rows(self):
        tar = os.urandom(3000)   # incompressible: the parts are real
        report = {"role": "db-admin", "claims": 2, "counts": {"in_scope": 3, "total": 3}, "needs_rendering": ["ka-note"], "skipped_no_roles_class": ["private"], "memory_dir": "/never/leaves"}
        calls: list = []

        def run(cmd, **kw):
            calls.append((cmd, kw))
            if "/m/broken" in cmd:
                raise subprocess.CalledProcessError(1, cmd, b"", b"harvest_memory: refusing rather than guessing where these belong:\n  private-secret.md")
            return subprocess.CompletedProcess(cmd, 0, tar, json.dumps(report).encode())
        dirs = [{"slug": "s-gzapp", "memory": "/m/gzapp", "files": 3, "working_copy": "/home/x/projects/gzapp"},
                {"slug": "s-stray", "memory": "/m/stray", "files": 1, "working_copy": None},
                {"slug": "s-broken", "memory": "/m/broken", "files": 1, "working_copy": "/home/x/projects/broken"}]
        m = ops.memory("/home/x", root="/r", run=run, dirs=dirs, all=True, part_bytes=1000)
        self.assertEqual((m["status"], len(m["bundles"])), ("ok", 3))
        ok, stray, broken = m["bundles"]
        self.assertEqual((ok["status"], ok["bytes"], ok["sha256"]), ("ok", 3000, hashlib.sha256(tar).hexdigest()))
        self.assertTrue(ok["parts"] >= 4 and len(ok["_parts"]) == ok["parts"], ok["parts"])
        self.assertTrue(all(len(p) == 1000 or i == len(ok["_parts"]) - 1 for i, p in enumerate(ok["_parts"])))
        raw = base64.b64decode("".join(ok["_parts"]))
        self.assertEqual(zlib.decompress(raw, 31), tar, "the parts reassemble to the tar")
        from unittest import mock
        with mock.patch("time.time", return_value=time.time() + 86400):
            later = ops.memory("/home/x", root="/r", run=lambda c, **k: subprocess.CompletedProcess(c, 0, tar, json.dumps(report).encode()), dirs=[dirs[0]], all=True, part_bytes=1000)["bundles"][0]["_parts"]
        self.assertEqual(later, ok["_parts"], "the gzip header carries no clock: the same tar is the same bytes")
        self.assertEqual(ok["report"], {"claims": 2, "counts": {"in_scope": 3, "total": 3}, "needs_rendering": ["ka-note"], "skipped_no_roles_class": ["private"]})
        self.assertNotIn("memory_dir", ok["report"], "only the whitelisted report keys travel")
        self.assertEqual(stray, {"slug": "s-stray", "files": 1, "status": "no-working-copy"})
        self.assertEqual(broken["status"], "harvest-failed")
        self.assertIn("refusing rather than guessing", broken["error"])
        self.assertEqual(len(calls), 2, "one run per harvestable directory, none for the stray")
        cmd, kw = calls[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1], "/r/tools/fabric/harvest_memory.py")
        self.assertEqual(cmd[2:], ["--bundle", "-", "--memory", "/m/gzapp", "--working-copy", "/home/x/projects/gzapp", "--all"])
        self.assertEqual(kw["env"]["AGENT_FABRIC_ROOT"], "/r")
        self.assertTrue(kw["timeout"] and kw["max_bytes"], "bounded in time and in bytes")
        no_all: list = []
        ops.memory("/home/x", root="/r", run=lambda c, **k: (no_all.append(c), subprocess.CompletedProcess(c, 0, tar, b"not json"))[1], dirs=[dirs[0]])
        self.assertNotIn("--all", no_all[0], "the watermark applies unless asked")
        self.assertEqual(ops.MEMORY_PART_BYTES, 90 * 1024, "under the relay's 128 KiB message limit with the envelope")
        whole = ops.memory("/home/x", root="/r", run=run, dirs=[dirs[0]])
        self.assertEqual(whole["bundles"][0]["parts"], 1, "a 3 KB tar is one part at the real size")

    def test_a_harvest_that_failed_with_nothing_on_stderr_says_why(self):
        def timeout(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 120)
        m = ops.memory("/home/x", root="/r", run=timeout, dirs=[{"slug": "s", "memory": "/m", "files": 1, "working_copy": "/w"}])
        self.assertEqual(m["bundles"][0]["status"], "harvest-failed")
        self.assertNotEqual(m["bundles"][0]["error"], "", "a timeout is named, where the Node said nothing")


class Languages(Base):
    def test_a_token_count_past_a_double_is_zero_not_a_failed_section(self):
        self.assertEqual(usage_mod._num0("9" * 400), 0)
        self.assertEqual(usage_mod._num0(int("9" * 400)), 0)
        self.assertEqual(usage_mod._num0(12), 12)

    def test_a_detector_percent_that_is_not_a_number_does_not_fail_the_section(self):
        h = self.scratch("lang-nan-")
        write(ops.langid_cmd(h, "/r")[0], "")
        run = lambda c, **k: subprocess.CompletedProcess(c, 0, json.dumps([[True, 90, [["en", "x"]]]]).encode(), b"")  # noqa: E731
        lg = ops.languages(["An English paragraph long enough to be judged here"], home=h, root="/r", run=run)
        self.assertEqual((lg["status"], lg["shares"], lg["dominant"]), ("ok", lg["shares"], {"en": 1}))
        self.assertEqual(util.js_json(lg["shares"]), '{"en":null}', "NaN is null on the wire, as JSON.stringify wrote it")

    def test_cld2_judges_only_paragraphs_of_twenty_letters_shares_weighted_by_letters_no_venv_is_unavailable(self):
        h = self.scratch("lang-home-")
        self.assertEqual(ops.languages(["ქართული აბზაცი საკმაოდ გრძელი"], home=h)["status"], "unavailable")
        venv_py = ops.langid_cmd(h, "/r")[0]
        write(venv_py, "")
        self.assertEqual(ops.langid_cmd(h, "/r")[1], "/r/runtime/langid/langid.py")
        seen: list = []
        paras = ["ქართული აბზაცი, საკმაოდ გრძელი რომ განისაჯოს", "An English paragraph long enough to be judged here", "ops.mjs:294 memory() exec harvest --bundle -",
                 "ნახევარი ქართული ნახევარი and half of it English text", "ok"]

        def run(cmd, **kw):
            seen.append((cmd, json.loads(kw["input"])))
            return subprocess.CompletedProcess(cmd, 0, json.dumps([[True, 90, [["ka", 100]]], [True, 50, [["en", 98]]], [False, 40, []], [True, 60, [["ka", 56], ["en", 43]]]]).encode(), b"")
        lg = ops.languages(paras, home=h, root="/r", run=run)
        self.assertEqual((lg["status"], lg["paragraphs"], lg["unreliable"]), ("ok", 4, 1))
        self.assertEqual(lg["dominant"], {"ka": 2, "en": 1})
        self.assertTrue(lg["shares"]["ka"] > lg["shares"]["en"] and 95 < lg["shares"]["ka"] + lg["shares"]["en"] <= 100, lg["shares"])
        self.assertEqual(list(lg["shares"]), ["ka", "en"], "sorted by share")
        self.assertEqual((seen[0][0], len(seen[0][1])), ([venv_py, "/r/runtime/langid/langid.py"], 4), "the two-letter answer is not sent")
        self.assertEqual(ops.languages([], home=h, root="/r", run=run), {"status": "ok", "paragraphs": 0, "unreliable": 0, "shares": {}, "dominant": {}})

        def no_pycld2(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, b"", b"langid: no pycld2 in this interpreter (runtime/langid/install.sh)\n")
        self.assertEqual(ops.languages([paras[1]], home=h, root="/r", run=no_pycld2)["why"], "langid: no pycld2 in this interpreter (runtime/langid/install.sh)")
        self.assertEqual(ops.languages([paras[1]], home=h, root="/r", run=lambda c, **k: subprocess.CompletedProcess(c, 0, b"nope", b""))["status"], "unavailable")
        self.assertEqual(ops.languages([paras[1]], home=h, root="/r", run=lambda c, **k: subprocess.CompletedProcess(c, 0, b"[]", b""))["status"], "unavailable", "a verdict count that does not match is not read")


class Tokens(Base):
    def test_per_model_deduplicated_by_request_in_the_window_direct_and_broker_apart_synthetic_dropped(self):
        h = self.home()
        now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc).timestamp() * 1000
        proj = os.path.join(h, ".claude", "projects", "-home-x-projects-gzapp")
        sub = os.path.join(proj, "s1", "subagents")
        os.makedirs(sub)
        n = [0]

        def rec(ts, model, u, req=None, mid=None):
            n[0] += 1
            return json.dumps({"type": "assistant", "timestamp": iso(ts), "requestId": req,
                               "message": {"id": mid or f"m-{n[0]}", "model": model, "usage": u, "content": [{"type": "text", "text": "SECRET-TEXT-NEVER-COUNTED"}]}}) + "\n"
        u1 = {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 20}
        write(os.path.join(proj, "s1.jsonl"),
              rec(now - DAY, "claude-opus-5", u1, "r1") + rec(now - DAY, "claude-opus-5", u1, "r1")
              + rec(now - 2 * DAY, "z-ai/glm-5.3", {"input_tokens": 500, "output_tokens": 5}, "r2")
              + rec(now - 30 * DAY, "claude-opus-5", u1, "r-old")
              + rec(now - DAY, "<synthetic>", {"input_tokens": 0, "output_tokens": 0}, "r-syn")
              + json.dumps({"type": "user", "message": {"content": "hi"}}) + "\nnot json\n")
        write(os.path.join(sub, "agent-a1.jsonl"), rec(now - DAY, "claude-sonnet-5", {"input_tokens": 1, "cache_read_input_tokens": 50, "output_tokens": 7}, mid="msg-sub"))
        stale = write(os.path.join(proj, "old.jsonl"), rec(now - DAY, "claude-opus-5", u1, "r-stale"))
        touch(stale, now - 40 * DAY)   # a file older than the window is not read
        t = ops.tokens(h, now=now)
        self.assertEqual((t["status"], t["days"]), ("ok", 7))
        self.assertEqual(t["requests"], {"session": 2, "subagent": 1})
        self.assertEqual(list(t["models"]), ["z-ai/glm-5.3", "claude-opus-5", "claude-sonnet-5"], "ordered by equivalents (525, 335, 41), synthetic absent")
        self.assertEqual(t["models"]["claude-opus-5"], {"requests": 1, "input": 10, "cache_write": 100, "cache_read": 1000, "output": 20, "equiv": 335, "path": "claude"})
        self.assertEqual(ops.equivalent({"input": 10, "cache_write": 100, "cache_read": 1000, "output": 20}), 10 + 125 + 100 + 100)
        self.assertEqual(t["models"]["z-ai/glm-5.3"], {"requests": 1, "input": 500, "cache_write": 0, "cache_read": 0, "output": 5, "equiv": 525, "path": "broker"})
        self.assertEqual(t["claude"], {"requests": 2, "input": 11, "cache_write": 100, "cache_read": 1050, "output": 27, "equiv": 335 + 41})
        self.assertEqual(t["broker"], {"requests": 1, "input": 500, "cache_write": 0, "cache_read": 0, "output": 5, "equiv": 525})
        self.assertIs(t["ratios"], ops.TOKEN_RATIOS)
        self.assertEqual((t["first"], t["last"]), (iso(now - 2 * DAY), iso(now - DAY)))
        self.assertNotIn("SECRET-TEXT", json.dumps(t), "counts only")
        self.assertEqual(ops.tokens(h, now=now, days=0.5)["status"], "no-records", "a narrower window with nothing in it says so")
        self.assertEqual(ops.tokens(self.scratch("ctl-empty-"))["status"], "no-records")
        c = ops.collect("tokens", {"home": h, "who": WHO, "days": 3})
        self.assertEqual(sorted(c), ["identity", "tokens"], "tokens rides with identity, so the coordinator can group by Claude account")
        self.assertEqual(c["tokens"]["days"], 3)


class Collect(Base):
    def test_status_is_every_section_a_single_op_its_own_and_a_failing_section_is_inline(self):
        h = self.home()
        calls: list[str] = []

        def run(cmd, **kw):
            calls.append(" ".join(cmd))
            raise OSError("boom")
        ctx = {"home": h, "who": WHO, "fetch": lambda *a, **k: usage_mod.Response(200, {}, b"{}"), "root": "/r", "run": run, "uid": 1}
        allr = ops.collect("status", ctx)
        self.assertEqual(sorted(allr), ["fabric", "identity", "keys", "session", "usage"])
        self.assertEqual(allr["fabric"]["status"], "not-a-checkout")
        self.assertEqual(allr["session"]["claude_processes"], 0)
        self.assert_no_secret(allr)
        calls.clear()
        one = ops.collect("keys", ctx)
        self.assertEqual(list(one), ["keys"])
        # run raises: the probe reads absent and never reaches a real git or gpg (review of #89: the
        # keyring of whoever runs the suite). Absent alone cannot show that — the real binaries read
        # absent too where no key is set — so the probe's question is asked of ctx.run, recorded.
        self.assertEqual(next(k for k in one["keys"] if k["name"] == keys_mod.SIGNING_ROW), {"name": keys_mod.SIGNING_ROW, "present": False})
        self.assertEqual(calls, ["git config --global user.signingkey"], "the signing probe went through ctx.run")
        self.assertTrue(all(o in ops.OPS for o in ("ping", "status", "memory")))
        self.assertNotIn("memory", allr, "a drain is asked for, never part of status")
        mem = ops.collect("memory", {"home": h, "run_bounded": lambda *a, **k: (_ for _ in ()).throw(AssertionError("never runs"))})
        self.assertEqual(mem, {"memory": {"status": "ok", "bundles": []}}, "a home with no memory answers an empty drain")
        self.assertEqual(ops.collect("ping", ctx), {}, "an op that names no section answers {}")

    def test_a_section_that_raises_is_said_inline_and_does_not_blank_the_reply(self):
        def boom(_c):
            raise RuntimeError("x" * 500)
        saved = ops.SECTIONS["keys"]
        ops.SECTIONS["keys"] = boom
        self.addCleanup(ops.SECTIONS.__setitem__, "keys", saved)
        r = ops.collect("status", {"home": self.home(), "who": WHO, "fetch": lambda *a, **k: usage_mod.Response(200, {}, b"{}"), "root": "/r", "run": lambda c, **k: (_ for _ in ()).throw(OSError("no")), "uid": 1})
        self.assertEqual(r["keys"], {"status": "failed", "error": "x" * 200})
        self.assertIn("identity", r)

    def test_collect_presence_answers_under_the_presence_key(self):
        data = ops.collect("presence", {"presence_opts": {"run": lambda c, **k: done(""), "who": {"agent": "web-dev-01", "host": "h", "role": "web-dev", "binding": "/nonexistent"}, "binding": {}}})
        self.assertEqual(list(data), ["presence"])
        self.assertEqual(data["presence"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
