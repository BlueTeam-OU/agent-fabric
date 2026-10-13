#!/usr/bin/env python3
"""tools/fabric/watch_identity.py: the persona, the harness and the model the identity header shows, from a scratch store
checkout, a scratch claims file, a fake /proc and fake harness binaries (agent-fabric ADR-056 rules 1, 2 and 4).

Each case fails when its guard is removed: the name is "AI <first> <surname>" from the profile, "AI <surname>" from the
claims by the agent id, None otherwise, and never without the AI; a profile that is not text of a sane length is no
profile; the avatar is the accepted file, else the candidate the profile names, a link or a directory in either place
is none; the store's env/ is never opened or listed; the harness is the one this account runs (claude first), by
/proc comm and the effective uid of the process; the version is the first line of `--version` of the binary on PATH, a
failing or missing one None; the model lines come from fabric-status's document and are None where it says nothing."""
from __future__ import annotations

import builtins
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import watch_identity as wi  # noqa: E402

AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
OTHER = "01a0f782-7e06-7dee-811f-0a860ed93bf4"


def write(path: str, data: str | bytes, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as fh:
        fh.write(data)
    os.chmod(path, mode)


class Persona(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-id-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "store")
        self.avatars = os.path.join(self.tmp, "avatars")
        self.claims = os.path.join(self.tmp, "claims.json")
        self.environ = {"HOME": self.tmp, "AGENT_FABRIC_SECRET_STORE": self.store}
        write(os.path.join(self.store, ".agent-id"), AGENT + "\n")

    def persona(self):
        return wi.persona(self.environ, self.claims, self.avatars)

    def profile(self, **over):
        doc = {"version": 1, "agent_id": AGENT, "first_name": "June", "surname": "Leavitt", "sex": "F",
               "avatar": {"file": "settings/avatar.png", "sha256": "0" * 64, "candidate": 1}, "accepted": "2026-10-13"}
        doc.update(over)
        write(os.path.join(self.store, "settings", "profile.json"), json.dumps(doc))

    def test_the_profile_gives_the_full_name_behind_the_ai(self):
        self.profile()
        write(self.claims, json.dumps({"claims": {AGENT: "Noether"}}))
        self.assertEqual(self.persona().name, "AI June Noether", "the claimed surname wins over the profile's")

    def test_without_a_profile_the_claimed_surname_gives_ai_surname(self):
        write(self.claims, json.dumps({"claims": {AGENT: "Leavitt", OTHER: "Boole"}}))
        self.assertEqual(self.persona().name, "AI Leavitt")

    def test_with_neither_there_is_no_name_and_never_a_name_without_the_ai(self):
        self.assertIsNone(self.persona().name)
        write(self.claims, json.dumps({"claims": {OTHER: "Boole"}}))
        self.assertIsNone(self.persona().name, "another agent's claim is not mine")
        os.remove(os.path.join(self.store, ".agent-id"))
        write(self.claims, json.dumps({"claims": {AGENT: "Leavitt"}}))
        self.assertIsNone(self.persona().name, "no agent id, no claim")

    def test_the_claimed_surname_wins_over_the_profiles_and_a_linked_settings_directory_is_not_followed(self):
        self.profile(surname="Wrong")
        write(self.claims, json.dumps({"claims": {AGENT: "Leavitt"}}))
        self.assertEqual(self.persona().name, "AI June Leavitt")
        elsewhere = os.path.join(self.tmp, "elsewhere")
        shutil.move(os.path.join(self.store, "settings"), elsewhere)
        write(os.path.join(elsewhere, "avatar.png"), b"x")
        os.symlink(elsewhere, os.path.join(self.store, "settings"))
        p = self.persona()
        self.assertEqual((p.name, p.avatar_path), ("AI Leavitt", None), "neither the profile nor the avatar is read through the link")

    def test_a_name_that_is_not_plain_text_of_a_sane_length_is_not_one(self):
        write(self.claims, json.dumps({"claims": {AGENT: "Leavitt"}}))
        for label, over in (("a control character", {"first_name": "Ju\x1b[2Jne"}), ("empty", {"surname": ""}), ("a number", {"first_name": 7}),
                            ("too long", {"surname": "x" * (wi.NAME_MAX + 1)}), ("a newline", {"first_name": "June\nAI Hacker"})):
            with self.subTest(label):
                self.profile(**over)
                want = "AI June Leavitt" if "first_name" not in over else "AI Leavitt"       # the claim fills in a surname that is none
                self.assertEqual(self.persona().name, want)
        write(os.path.join(self.store, "settings", "profile.json"), "{not json")
        self.assertEqual(self.persona().name, "AI Leavitt")
        write(os.path.join(self.store, "settings", "profile.json"), "[1, 2]")
        self.assertEqual(self.persona().name, "AI Leavitt")

    def test_a_malformed_agent_id_or_claims_file_gives_no_name(self):
        write(os.path.join(self.store, ".agent-id"), "not-an-id\n")
        write(self.claims, json.dumps({"claims": {"not-an-id": "Leavitt"}}))
        self.assertIsNone(self.persona().name)
        write(os.path.join(self.store, ".agent-id"), AGENT)
        for text in ("{nope", "[]", json.dumps({"claims": [AGENT]}), json.dumps({"claims": {AGENT: ["Leavitt"]}})):
            with self.subTest(text):
                write(self.claims, text)
                self.assertIsNone(self.persona().name)

    def test_the_avatar_is_the_accepted_file_else_the_candidate_the_profile_names(self):
        self.profile()
        self.assertIsNone(self.persona().avatar_path, "nothing at either place")
        write(os.path.join(self.avatars, AGENT, "1.png"), b"candidate")
        self.assertEqual(self.persona().avatar_path, os.path.join(self.avatars, AGENT, "1.png"))
        write(os.path.join(self.store, "settings", "avatar.png"), b"accepted")
        self.assertEqual(self.persona().avatar_path, os.path.join(self.store, "settings", "avatar.png"))

    def test_a_candidate_is_only_the_one_the_profile_names_and_only_for_a_real_profile(self):
        write(os.path.join(self.avatars, AGENT, "1.png"), b"candidate")
        self.assertIsNone(self.persona().avatar_path, "no profile: no candidate is named")
        for bad in (0, -1, 1000, "1", True, None):
            with self.subTest(bad):
                self.profile(avatar={"file": "settings/avatar.png", "sha256": "0" * 64, "candidate": bad})
                self.assertIsNone(self.persona().avatar_path)
        self.profile(avatar={"file": "settings/avatar.png", "sha256": "0" * 64, "candidate": 2})
        self.assertIsNone(self.persona().avatar_path, "candidate 2 is not at the place")

    def test_a_link_or_a_directory_in_place_of_the_avatar_is_none(self):
        self.profile()
        real = os.path.join(self.tmp, "real.png")
        write(real, b"x")
        os.makedirs(os.path.join(self.store, "settings"), exist_ok=True)
        os.symlink(real, os.path.join(self.store, "settings", "avatar.png"))
        self.assertIsNone(self.persona().avatar_path)
        os.remove(os.path.join(self.store, "settings", "avatar.png"))
        os.makedirs(os.path.join(self.store, "settings", "avatar.png"))
        self.assertIsNone(self.persona().avatar_path)
        os.rmdir(os.path.join(self.store, "settings", "avatar.png"))
        os.makedirs(os.path.join(self.avatars, AGENT))
        os.symlink(real, os.path.join(self.avatars, AGENT, "1.png"))
        self.assertIsNone(self.persona().avatar_path)

    def test_the_stores_secrets_are_never_opened_or_listed(self):
        self.profile()
        write(os.path.join(self.store, "env", "GH_TOKEN.gpg"), b"encrypted")
        write(os.path.join(self.store, "recovery", "key.asc"), b"key")
        write(os.path.join(self.store, ".gpg-id"), "FPR\n")
        opened: list[str] = []
        listed: list[str] = []
        real_open, real_listdir, real_scandir = builtins.open, os.listdir, os.scandir
        builtins.open = lambda p, *a, **k: (opened.append(str(p)), real_open(p, *a, **k))[1]
        os.listdir = lambda p=".": (listed.append(str(p)), real_listdir(p))[1]
        os.scandir = lambda p=".": (listed.append(str(p)), real_scandir(p))[1]
        real_os_open = os.open
        os.open = lambda p, *a, **k: (opened.append(str(p)), real_os_open(p, *a, **k))[1]
        try:
            self.persona()
        finally:
            builtins.open, os.listdir, os.scandir, os.open = real_open, real_listdir, real_scandir, real_os_open
        touched = sorted({os.path.relpath(p, self.store) for p in opened + listed if p.startswith(self.store)})
        self.assertEqual(touched, [".agent-id", "settings/profile.json"], "the avatar is only stat'ed here; env/ and the rest are untouched")
        self.assertEqual([p for p in listed if p.startswith(self.store)], [], "the store is never listed")

    def test_the_default_store_is_under_home(self):
        self.assertEqual(wi.store_dir({"HOME": "/h"}), "/h/.local/share/agent-fabric/secrets")
        self.assertEqual(wi.store_dir({"HOME": "/h", "AGENT_FABRIC_SECRET_STORE": "/s"}), "/s")


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watch-harness-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def process(self, pid: int, comm: str, uid: int = 1000, euid: int | None = None) -> None:
        write(os.path.join(self.tmp, str(pid), "status"), f"Name:\t{comm}\nUid:\t{uid}\t{euid or uid}\t{uid}\t{uid}\n")

    def test_it_is_the_harness_this_account_runs_claude_before_codex(self):
        self.assertIsNone(wi.running_harness(1000, self.tmp))
        self.process(1, "bash")
        self.process(2, "codex")
        self.assertEqual(wi.running_harness(1000, self.tmp), "codex")
        self.process(3, "claude")
        self.assertEqual(wi.running_harness(1000, self.tmp), "claude")

    def test_another_accounts_harness_is_not_mine(self):
        self.process(1, "claude", uid=1001)
        self.assertIsNone(wi.running_harness(1000, self.tmp))
        self.process(2, "claude-code-guide")             # a name that merely starts with it
        self.assertIsNone(wi.running_harness(1000, self.tmp))

    def test_it_is_the_effective_uid_that_decides(self):
        self.process(1, "claude", uid=1000, euid=1001)
        self.assertIsNone(wi.running_harness(1000, self.tmp))
        self.process(2, "codex", uid=0, euid=1000)
        self.assertEqual(wi.running_harness(1000, self.tmp), "codex")

    def test_no_proc_is_none(self):
        self.assertIsNone(wi.running_harness(1000, os.path.join(self.tmp, "absent")))

    def test_the_version_is_the_first_line_of_the_binarys_own_answer(self):
        bindir = os.path.join(self.tmp, "bin")
        write(os.path.join(bindir, "claude"), "#!/bin/sh\n[ \"$*\" = --version ] || exit 9\necho '2.1.286 (Claude Code)'\necho 'second line'\n", 0o755)
        write(os.path.join(bindir, "codex"), "#!/bin/sh\necho 'usage: codex 9.9'\necho 'boom' >&2\nexit 4\n", 0o755)
        self.assertEqual(wi.version_line("claude", bindir), "2.1.286 (Claude Code)")
        self.assertIsNone(wi.version_line("codex", bindir), "a failing --version is no version")
        self.assertIsNone(wi.version_line("claude", os.path.join(self.tmp, "nowhere")), "not on PATH")

    def test_a_version_line_is_cut_and_stays_text_for_printable_to_judge(self):
        bindir = os.path.join(self.tmp, "bin")
        write(os.path.join(bindir, "claude"), "#!/bin/sh\nprintf '%s\\n' \"$(python3 -c \"print('v' * 500 + '\\x1b[2J')\")\"\n", 0o755)
        line = wi.version_line("claude", bindir)
        self.assertEqual(len(line), 80)


class Models(unittest.TestCase):
    def test_the_session_model_effort_and_the_second_engine_come_from_the_document(self):
        doc = {"api": {"session_model": "claude-x"}, "session_effort": {"asked": "low", "reported": "medium", "launched": "high"},
               "engines": {"openai code-review": "gpt-6.1-sol (from capabilities.providers.openai) effort high (sent on x)"}}
        self.assertEqual(wi.model_lines(doc), {"model": "claude-x", "effort": "medium", "engine": "openai code-review: gpt-6.1-sol"})

    def test_the_level_falls_back_through_reported_launched_asked_and_a_missing_key_is_none(self):
        self.assertEqual(wi.model_lines({"session_effort": {"launched": "high", "asked": "low"}})["effort"], "high")
        self.assertEqual(wi.model_lines({"session_effort": {"asked": "low"}})["effort"], "low")
        self.assertEqual(wi.model_lines({}), {"model": None, "effort": None, "engine": None})
        self.assertEqual(wi.model_lines(None), {"model": None, "effort": None, "engine": None})
        self.assertEqual(wi.model_lines({"api": {"session_model": 7}, "session_effort": {"reported": 3}, "engines": {}})["model"], None)


if __name__ == "__main__":
    unittest.main()
