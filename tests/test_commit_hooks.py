#!/usr/bin/env python3
"""tools/fabric/guards/commit_hooks.py: the internals tests/test_githooks_cli.py and tests/test_githook_*.py cannot reach, because they
drive the hooks with the pin present and a message that exists (Wave 9 batch 4; ADR-040 rule 5). Each case names the one-line mutation
it catches.

Forwarders (the hook files):
  a commit hook without the pin refuses the commit: 127 and the install line   - `exit 127` to `exit 0` in pre-commit or commit-msg
  post-commit without the pin says so and still exits 0                        - `exit 0` to `exit 127` in post-commit
Module, driven through the hooks as git runs them:
  a message file that cannot be read refuses the commit                        - the OSError branch of commit_msg returning 0
  post-commit never fails the commit: fabric-sign failing is said, exit 0      - `return 0` to `return 1` after the say in post_commit
  post-commit files the note for either signing program, by basename           - `rsplit("/", 1)[-1]` dropped, or gpg.ssh.program not read
  a repository neither git nor its layout can place is refused, not a project  - same_repository returning False there
Module, called directly:
  a locale path is the whole path (not found inside a longer one)              - `fullmatch` to `search`
  lines_of is mapfile's: no phantom line for empty output, no split on U+2028  - `.split("\\n")` to `.splitlines()`
  the typed Fabric-Role is the value up to the next colon, last trailer wins   - `re.split(": *"` to `partition(":")`
  a login holds a locale by the suffix after a hyphen or by being it           - `endswith("-" + suffix)` to `endswith(suffix)`
  a worktree's common directory is its clone's .git                            - the gitdir returned without reading `commondir`
"""
from __future__ import annotations

import os
import stat
import sys

# No bytecode in the tree: the modules imported below would leave __pycache__ beside them (review of #329, F7).
sys.dont_write_bytecode = True
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric", "guards"))
from githook_fixtures import Fabric, Repo  # noqa: E402
import commit_hooks as ch  # noqa: E402

NO_PIN = "/nonexistent/fabric-python"


class Hooks(unittest.TestCase):
    def setUp(self):
        self.fabric = Fabric()
        self.addCleanup(self.fabric.cleanup)
        self.repo = self.fabric.project()

    def stub(self, name: str, body: str) -> str:
        path = os.path.join(self.fabric.stubs, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path


class Forwarders(Hooks):
    def test_a_commit_hook_without_the_pin_refuses_and_prints_the_install_command(self):
        for hook, args in (("pre-commit", ()), ("commit-msg", ("MSG",))):
            with self.subTest(hook=hook):
                r = self.fabric.hook(hook, self.repo, *args, AGENT_FABRIC_PYTHON=NO_PIN)
                self.assertEqual(r.returncode, 127, r.stderr)
                self.assertIn(f"{hook}: the fleet's pinned Python is not installed at {NO_PIN}, so this commit is refused", r.stderr)
                self.assertIn("python_pin.py install", r.stderr)

    def test_post_commit_without_the_pin_says_so_and_exits_zero(self):
        r = self.fabric.hook("post-commit", self.repo, AGENT_FABRIC_PYTHON=NO_PIN)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("post-commit: the fleet's pinned Python is not installed", r.stderr)


class Module(Hooks):
    def test_a_message_file_that_cannot_be_read_refuses_the_commit(self):
        r = self.fabric.hook("commit-msg", self.repo, os.path.join(self.fabric.root, "no-such-message"))
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("commit-msg: cannot read the message file", r.stderr)

    def sign_with(self, key: str, value: str, note_exit: int):
        self.repo.git("config", key, value)
        self.stub("fabric-sign", f'echo "$@" >> "{self.fabric.root}/calls"\nexit {note_exit}\n')
        return self.fabric.hook("post-commit", self.repo)

    def calls(self) -> str:
        try:
            with open(os.path.join(self.fabric.root, "calls"), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def test_post_commit_never_fails_the_commit_when_the_note_cannot_be_filed(self):
        r = self.sign_with("gpg.program", "/opt/x/fabric-sign", 3)
        self.assertEqual((r.returncode, self.calls()), (0, "note HEAD\n"))
        self.assertIn("post-commit: no proof note yet for HEAD; the pre-push hook attaches it", r.stderr)

    def test_post_commit_files_the_note_for_the_ssh_signing_program_too_and_is_silent_when_it_works(self):
        r = self.sign_with("gpg.ssh.program", "fabric-sign", 0)
        self.assertEqual((r.returncode, r.stderr, self.calls()), (0, "", "note HEAD\n"))

    def test_post_commit_leaves_another_signing_program_alone(self):
        r = self.sign_with("gpg.program", "/usr/bin/gpg", 0)
        self.assertEqual((r.returncode, r.stderr, self.calls()), (0, "", ""))

    def test_a_commit_whose_repository_cannot_be_told_from_the_fabrics_is_refused_not_taken_for_a_project(self):
        # mutation: same_repository returning False when neither git nor the toplevel's layout names a common directory
        self.fabric.itself()
        nowhere = os.path.join(self.fabric.root, "no-checkout")
        os.makedirs(nowhere)
        self.stub("git", f'[ "$1" = rev-parse ] && [ "$2" = --git-common-dir ] && exit 128\n'
                         f'[ "$1" = rev-parse ] && [ "$2" = --show-toplevel ] && {{ echo "{nowhere}"; exit 0; }}\nexec /usr/bin/git "$@"\n')
        self.repo.stage("src/a.txt")
        self.fabric.bind("backend-dev")
        r = self.fabric.hook("pre-commit", self.repo)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("commit hooks: cannot tell whether this commit is made in agent-fabric", r.stderr)


class Direct(unittest.TestCase):
    def test_a_unicode_space_does_not_hide_an_attribution(self):
        # mutation: an ASCII-only whitespace class, which admitted an em-spaced trailer and footer the bash refused (#329 F2)
        self.assertTrue(ch._banned_attribution("x\n\n\u2003Co-authored-by: a <a@b>\n"))
        self.assertTrue(ch._banned_attribution("x\n\nGenerated with\u2003[Claude Code](https://x)\n"))
        self.assertFalse(ch._banned_attribution("x\n\nKind: work\n"))

    def test_the_role_stamp_sees_a_trailer_where_grep_space_did_and_only_there(self):
        # mutation: the ban's wider class used for the stamp, so an NBSP-led line skipped the stamp the bash wrote (#329 r2)
        self.assertTrue(ch.FABRIC_ROLE_RE.match("\u2003Fabric-Role: x"))
        for lead in ("\u00a0", "\u2007", "\u202f", "\x1c", "\x85"):
            self.assertFalse(ch.FABRIC_ROLE_RE.match(lead + "Fabric-Role: x"), repr(lead))

    def test_a_locale_path_is_the_whole_path(self):
        ok = "identities/roles/language-culture/locale/ge/a.md"
        self.assertEqual(ch.locale_role([ok]), ("language-culture", "ge"))
        self.assertIsNone(ch.locale_role(["vendor/" + ok]))
        self.assertIsNone(ch.locale_role([ok + "/deeper.md"]))
        self.assertIsNone(ch.locale_role([]))

    def test_the_shared_prompt_pieces_belong_to_language_culture_and_one_suffix_only(self):
        self.assertEqual(ch.locale_role(["identities/prompt/locale/ge/x.md"]), ("language-culture", "ge"))
        self.assertIsNone(ch.locale_role(["identities/prompt/locale/ge/x.md", "identities/prompt/locale/de/x.md"]))
        self.assertIsNone(ch.locale_role(["identities/prompt/locale/ge/x.md", "identities/roles/web-dev/locale/ge/x.md"]))

    def test_lines_of_is_mapfiles(self):
        self.assertEqual(ch.lines_of(""), [])
        self.assertEqual(ch.lines_of("a\nb\n"), ["a", "b"])
        self.assertEqual(ch.lines_of("a b\x0bc\n"), ["a b\x0bc"])

    def test_the_typed_role_is_the_value_up_to_the_next_colon_and_the_last_trailer_wins(self):
        import tempfile
        import shutil
        scratch = tempfile.mkdtemp(prefix="commit-hooks-test-")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        msg = os.path.join(scratch, "MSG")
        with open(msg, "w", encoding="utf-8") as fh:
            fh.write("s\n\nfabric-ROLE: first\nFabric-Role: second: tail\n")
        self.assertEqual(ch._typed_role(msg), "second")

    def test_a_checkouts_common_directory_is_its_clones_whether_it_is_the_clone_or_a_worktree_of_it(self):
        # mutation: a worktree's gitdir taken as its common directory (`commondir` not read), so a fabric root that is itself a
        # worktree stopped being the repository its clone's commits are made in
        repo = Repo()
        self.addCleanup(repo.cleanup)
        wt = repo.worktree("feat")
        clone = os.path.realpath(os.path.join(repo.path, ".git"))
        self.assertEqual((ch._common_dir_of(repo.path), ch._common_dir_of(wt.path)), (clone, clone))
        self.assertEqual(ch._common_dir_of(repo.root), "")

    def test_a_login_holds_a_locale_by_the_suffix_after_a_hyphen_or_by_being_it(self):
        self.assertTrue(ch._holds_locale("language-culture-ge", "ge"))
        self.assertTrue(ch._holds_locale("ge", "ge"))
        self.assertFalse(ch._holds_locale("language-culturege", "ge"))


if __name__ == "__main__":
    unittest.main()
