#!/usr/bin/env python3
"""policies/githooks/locale-carve-out.sh: the library pre-commit, commit-msg and (as a regex) the CI authority check use to decide
whether a commit falls, every path of it, under ONE locale's translations identities/roles/<role>/locale/<suffix>/ (Wave 9 batch 4;
ADR-040 rule 5). It has no bash test of its own; this file characterises its two functions the way the hooks call them (sourced, under
`set -uo pipefail`). The library is ONE constant, LIB (GITHOOKS_DIR/locale-carve-out.sh; GITHOOKS_DIR overrides the directory).

locale_carve_out_role PATH...   returns 0 and sets locale_role and locale_suffix when every path is a file directly inside one locale
                                directory of one role; 1 otherwise: no path at all, any other path, two roles, two suffixes, a path
                                deeper than the locale directory. The variables mean something only on 0 (after a failure they are
                                cleared on a role/suffix mismatch and on a bad first path, and unspecified after a later bad path).
                                Role and suffix are lower-case words: [a-z][a-z0-9-]*; the file name is any single name.
locale_carve_out_paths          the staged paths to judge, one per line: normally what is staged against HEAD (added, copied, deleted,
                                modified, renamed, type-changed; renames off, so a move shows source and destination); for a merge in
                                progress what the staged tree adds over the MERGED-IN side (MERGE_HEAD) - the branch's own content, not
                                the union the index shows, so a translation branch can take main in once main has moved (the ge holder,
                                2026-09-18); nothing, quietly, outside a repository.

Mutations each case fails on (planted on the file as formatted): making the file part `[^/]*` instead of `[^/]+` (a directory with
no file); anchoring the role loosely, `[a-z]` for `[a-z][a-z0-9-]*` (role shapes); dropping the second-path comparison (two roles / two
suffixes); letting an empty argument list return 0 (no path at all); diffing the merge against HEAD instead of MERGE_HEAD (merge); dropping
`--no-renames` (a move shows only its destination); `--diff-filter=ACDMRT` to `ACMRT` (a deletion is a path)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import GITHOOKS_DIR, Repo, call_library  # noqa: E402

LIB = os.path.join(GITHOOKS_DIR, "locale-carve-out.sh")
LOCALE = "identities/roles/language-culture/locale/ge/"


class Role(unittest.TestCase):
    def setUp(self):
        self.repo = Repo({"README": "r\n"})
        self.addCleanup(self.repo.cleanup)

    def ask(self, *paths: str) -> tuple[int, str, str]:
        r = call_library(LIB, self.repo.path, 'locale_carve_out_role "$@"; rc=$?; printf "%s|%s|%s\\n" "$rc" "$locale_role" "$locale_suffix"', *paths)
        self.assertEqual(r.stderr, "")
        rc, role, suffix = r.stdout.strip().split("|")
        return int(rc), role, suffix

    def test_one_locale_file_is_the_carve_out_and_names_its_role_and_suffix(self):
        self.assertEqual(self.ask(LOCALE + "harness.md"), (0, "language-culture", "ge"))

    def test_many_files_of_one_locale_are_one_carve_out(self):
        self.assertEqual(self.ask(LOCALE + "a.md", LOCALE + "b.md", LOCALE + "has space.md", LOCALE + "ünï.md"), (0, "language-culture", "ge"))

    def test_role_and_suffix_may_hold_digits_and_hyphens_after_a_letter(self):
        self.assertEqual(self.ask("identities/roles/web-dev2/locale/ge-2/x"), (0, "web-dev2", "ge-2"))

    def test_no_path_at_all_is_not_a_carve_out(self):
        rc, role, suffix = self.ask()
        self.assertEqual((rc, role, suffix), (1, "", ""))

    def test_any_other_path_is_not_a_carve_out(self):
        for bad in ("src/a.py", "identities/roles/language-culture/charter.md", "identities/roles/language-culture/locale/charter.md",
                    "./" + LOCALE + "x.md", "/" + LOCALE + "x.md", LOCALE + "x.md/", "identities/roles/language-culture/locale/ge",
                    "xidentities/roles/language-culture/locale/ge/x.md"):
            with self.subTest(path=bad):
                self.assertEqual(self.ask(bad)[0], 1)
                self.assertEqual(self.ask(LOCALE + "ok.md", bad)[0], 1)

    def test_a_directory_with_no_file_and_a_path_deeper_than_the_locale_directory_are_not_a_carve_out(self):
        self.assertEqual(self.ask(LOCALE)[0], 1)
        self.assertEqual(self.ask(LOCALE + "sub/x.md")[0], 1)

    def test_role_and_suffix_are_lower_case_words_starting_with_a_letter(self):
        for bad in ("identities/roles/Language/locale/ge/x", "identities/roles/1abc/locale/ge/x", "identities/roles/a_b/locale/ge/x",
                    "identities/roles/a/locale/Ge/x", "identities/roles/a/locale/9/x", "identities/roles//locale/ge/x",
                    "identities/roles/a/locale//x", "identities/roles/a.b/locale/ge/x"):
            with self.subTest(path=bad):
                self.assertEqual(self.ask(bad)[0], 1)

    def test_two_roles_or_two_suffixes_are_two_carve_outs_so_none_and_the_variables_are_cleared(self):
        self.assertEqual(self.ask(LOCALE + "x", "identities/roles/web-dev/locale/ge/x"), (1, "", ""))
        self.assertEqual(self.ask(LOCALE + "x", "identities/roles/language-culture/locale/ka/x"), (1, "", ""))

    def test_a_path_that_is_not_a_locale_first_leaves_the_variables_empty(self):
        self.assertEqual(self.ask("src/a.py", LOCALE + "x"), (1, "", ""))

    def test_the_shared_prompt_pieces_translations_are_language_cultures(self):
        # identities/prompt/locale/<lang>/ (ADR-060 stage 3) is written by the
        # language-culture holder named for <lang>, alone or with its own locale.
        prompt = "identities/prompt/locale/ge/"
        self.assertEqual(self.ask(prompt + "team.md", prompt + "memory.md"), (0, "language-culture", "ge"))
        self.assertEqual(self.ask(prompt + "team.md", LOCALE + "charter.md"), (0, "language-culture", "ge"))
        self.assertEqual(self.ask(prompt + "team.md", "identities/prompt/locale/ru/team.md"), (1, "", ""))
        self.assertEqual(self.ask(prompt + "team.md", "identities/roles/legal-expert/locale/ge/charter.md"), (1, "", ""))
        for bad in ("identities/prompt/team.md", prompt + "d/x.md", "identities/prompt/locale/Ge/x", "identities/promptx/locale/ge/x"):
            with self.subTest(bad=bad):
                self.assertEqual(self.ask(bad)[0], 1)


class Paths(unittest.TestCase):
    def setUp(self):
        self.repo = Repo({"README": "r\n", LOCALE + "old.md": "old\n", "src/a.py": "a\n"})
        self.addCleanup(self.repo.cleanup)

    def paths(self) -> list[str]:
        r = call_library(LIB, self.repo.path, "locale_carve_out_paths")
        self.assertEqual(r.stderr, "")
        return r.stdout.splitlines()

    def test_nothing_staged_is_no_path(self):
        self.assertEqual(self.paths(), [])

    def test_the_staged_paths_are_listed_one_per_line_in_git_order(self):
        self.repo.stage(LOCALE + "new.md")
        self.repo.stage("src/b.py")
        self.assertEqual(self.paths(), [LOCALE + "new.md", "src/b.py"])

    def test_a_deletion_and_a_type_change_are_paths_too(self):
        self.repo.git("rm", "-q", LOCALE + "old.md")
        os.remove(os.path.join(self.repo.path, "src/a.py"))
        os.symlink("../README", os.path.join(self.repo.path, "src/a.py"))
        self.repo.git("add", "-A")
        self.assertEqual(self.paths(), [LOCALE + "old.md", "src/a.py"])

    def test_a_rename_is_its_source_and_its_destination(self):
        self.repo.git("mv", LOCALE + "old.md", "src/moved.md")
        self.assertEqual(self.paths(), [LOCALE + "old.md", "src/moved.md"])

    def test_outside_a_repository_it_prints_nothing_and_says_nothing(self):
        plain = os.path.join(self.repo.root, "plain")
        os.makedirs(plain)
        r = call_library(LIB, plain, "locale_carve_out_paths", ceiling=self.repo.root)
        self.assertEqual((r.stdout, r.stderr), ("", ""))

    def test_a_merge_in_progress_is_judged_by_what_the_branch_adds_over_the_merged_in_side(self):
        # main moves on (other paths); the holder's translation branch took its own commit and now folds main in
        self.repo.git("checkout", "-q", "-b", "locale-ge")
        self.repo.commit(LOCALE + "branch.md", "translated\n", message="translation")
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("src/main_only.py", "m\n", message="main moves")
        self.repo.git("checkout", "-q", "locale-ge")
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", "main", check=False)
        self.assertTrue(os.path.exists(os.path.join(self.repo.path, ".git", "MERGE_HEAD")), "precondition: a merge is in progress")
        self.assertEqual(self.repo.git("diff", "--cached", "--name-only", "HEAD").stdout.split(), ["src/main_only.py"], "precondition: the index differs from HEAD by main's path")
        self.assertEqual(self.paths(), [LOCALE + "branch.md"])

    def test_a_move_the_branch_made_is_listed_by_its_source_and_its_destination_in_a_merge_too(self):
        self.repo.git("checkout", "-q", "-b", "locale-ge")
        self.repo.git("mv", LOCALE + "old.md", LOCALE + "renamed.md")
        self.repo.git("commit", "-qm", "rename within the locale")
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("src/main_only.py", "m\n", message="main moves")
        self.repo.git("checkout", "-q", "locale-ge")
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", "main", check=False)
        self.assertEqual(self.paths(), [LOCALE + "old.md", LOCALE + "renamed.md"])

    def test_a_hand_edit_outside_the_locale_during_the_merge_is_a_path(self):
        self.repo.git("checkout", "-q", "-b", "locale-ge")
        self.repo.commit(LOCALE + "branch.md", "translated\n", message="translation")
        self.repo.git("checkout", "-q", "main")
        self.repo.commit("src/main_only.py", "m\n", message="main moves")
        self.repo.git("checkout", "-q", "locale-ge")
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", "main", check=False)
        self.repo.stage("src/a.py", "edited by hand\n")
        self.assertEqual(self.paths(), [LOCALE + "branch.md", "src/a.py"])


if __name__ == "__main__":
    unittest.main()
