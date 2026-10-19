#!/usr/bin/env python3
"""policies/githooks/commit-msg: refuses a message carrying machine attribution, refuses a change to what the fabric-coordinator role
guards unless the live binding holds the owning role (or a carve-out admits it), and records the binding as the Fabric-Role trailer
(Wave 9 batch 4; ADR-040 rule 5). It has no bash test of its own; tests/test_githooks_cli.py drives it through `git commit` and pins the
fence, the locale carve-out and the Kind: rule (about seventy checks, GITHOOKS_DIR convention). This file adds what that one does not pin,
driving the hook as git does - by path, from the repository, with the message file as its one argument - so it runs unchanged against the
bash today and against the Python module later. The seam is ONE constant, githook_fixtures.GITHOOKS_DIR (the directory under test, default policies/githooks; the GITHOOKS_DIR
environment variable overrides it), and the hook is its commit-msg file; the login the hook sees is a stand-in `id` first on PATH (githook_fixtures.LOGIN), so the file passes on any account. The fabric under test is a scratch root holding a COPY of the hooks, its own policies/authority.json, and links to the real
runtime/ and tools/ (githook_fixtures.Fabric), so each case chooses the owner role, the contributors and the binding.

Carried here (each is a method): the banned-attribution family (a trailer in any case or indented, a mid-line mention is no trailer, the
generated-with footer with any spacing or split over lines, a session URL anywhere, comment lines ignored, both reasons at once, the message
file untouched when refused, the check running before everything else); the refusal of a guarded change by an unbound or other-role session,
naming the held role and the owner; the owner role READ from authority.json and defaulting to fabric-coordinator when the file is missing or
unreadable; the typed-trailer mismatch message and "the last trailer wins"; the Fabric-Role trailer written after Kind:, not doubled, not
written when no role is held, not written over an existing one in any case (an indented one folds into the previous trailer's value in git, so the Kind rule refuses it first); the locale carve-out's login test; the contributor carve-out's
three outcomes; a missing argument.

Mutations each case fails on (planted on the hook as formatted): `grep -v '^#'` to `cat` (comment lines); `TRAILER_RE` anchored without the
leading whitespace (indented trailer); `tr '\n\r' '  '` to `tr -d '\n\r'` (a footer split over lines); reading the owner role from a constant
(authority.json); the comparison `"$typed" != "$role"` to `!=` on lower-case (mismatch); the `git interpret-trailers --in-place` call replaced by `true` (the trailer is written); `grep -qiE`
to `grep -qE` (an existing trailer in another case); `contributor=$?` dropped (contributor carve-out); the banned check moved after the guard
(order)."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import HOST, LOGIN, Fabric  # noqa: E402

KIND = "\n\nKind: work"
LOCALE_FILE = "identities/roles/language-culture/locale/dev-03/harness.md"


class Hook(unittest.TestCase):
    owner = "fabric-coordinator"

    def setUp(self):
        self.fabric = Fabric(owner_role=self.owner)
        self.addCleanup(self.fabric.cleanup)
        self.repo = self.fabric.project()
        self.n = 0

    def message(self, text: str) -> str:
        self.n += 1
        path = os.path.join(self.fabric.root, f"MSG{self.n}")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def run_hook(self, text: str, repo=None, **extra):
        path = self.message(text)
        r = self.fabric.hook("commit-msg", repo or self.repo, path, **extra)
        with open(path, encoding="utf-8", newline="") as fh:
            return r, fh.read()

    def stage_guarded(self, repo=None, rel=".agent-fabric/memory/backend-dev/workflow.md"):
        (repo or self.repo).stage(rel)


class BannedAttribution(Hook):
    def refused(self, text, *reasons):
        r, after = self.run_hook(text + KIND)
        self.assertEqual(r.returncode, 1, r.stderr)
        for reason in reasons:
            self.assertIn(reason, r.stderr)
        self.assertEqual(after, text + KIND, "a refused message is left as it was")
        return r

    TRAILER = "commit-msg: the message carries a banned attribution trailer (Co-authored-by / Claude-Session)."
    FOOTER = "commit-msg: the message carries a generated-with footer or a session URL."

    def test_a_coauthored_by_or_claude_session_trailer_is_refused_in_any_case_and_indented(self):
        for line in ("Co-authored-by: A <a@example.invalid>", "co-AUTHORED-BY: A", "   Co-authored-by: A", "\tClaude-Session: abc",
                     "Claude-Session: https://example.invalid/x"):
            with self.subTest(line=line):
                r = self.refused(f"subject\n\nbody\n\n{line}", self.TRAILER)
                self.assertNotIn(self.FOOTER, r.stderr)

    def test_the_refusal_explains_itself_and_ends_with_what_to_do(self):
        r = self.refused("subject\n\nCo-authored-by: A", self.TRAILER, 'The repo authors its own history (AGENTS.md, "Git discipline").',
                         "Remove the lines and commit again.")
        self.assertEqual(r.stdout, "")

    def test_a_mention_in_a_sentence_is_not_a_trailer(self):
        for text in ("subject\n\nplease do not add Co-authored-by: lines", "subject\n\nthe Claude-Session: header is banned"):
            with self.subTest(text=text):
                r, _ = self.run_hook(text + KIND)
                self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_generated_with_footer_is_refused_with_any_spacing_case_or_line_break(self):
        for footer in ("Generated with [Claude Code](https://claude.com/claude-code)", "Generated with   [Claude Code]", "generated WITH [claude code]",
                       "Generated with\n[Claude Code]", "Generated with\r\n[Claude Code]"):
            with self.subTest(footer=footer):
                r = self.refused(f"subject\n\n{footer}", self.FOOTER)
                self.assertNotIn(self.TRAILER, r.stderr)

    def test_a_session_url_is_refused_anywhere_in_the_message(self):
        for text in ("subject\n\nsee https://claude.ai/code/session_01abc for context", "https://claude.ai/code/session_x\n\nsubject",
                     "subject\n\nCLAUDE.AI/CODE/SESSION_ABC"):
            with self.subTest(text=text):
                self.refused(text, self.FOOTER)

    def test_a_message_with_both_says_both_and_exits_once(self):
        r = self.refused("subject\n\nGenerated with [Claude Code]\n\nCo-authored-by: A", self.TRAILER, self.FOOTER)
        self.assertEqual(r.stderr.count("Remove the lines and commit again."), 1)
        self.assertLess(r.stderr.index(self.TRAILER), r.stderr.index(self.FOOTER))

    def test_comment_lines_are_not_part_of_the_message(self):
        text = "subject\n\n# Co-authored-by: A\n#Generated with [Claude Code]\n# https://claude.ai/code/session_x" + KIND
        r, _ = self.run_hook(text)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_the_check_runs_before_the_fence_and_before_the_kind_rule(self):
        self.stage_guarded()
        r, _ = self.run_hook("subject\n\nCo-authored-by: A", AGENT_FABRIC_STATE_DIR=self.fabric.state)       # no Kind, a guarded change
        self.assertEqual(r.returncode, 1)
        self.assertIn(self.TRAILER, r.stderr)
        self.assertNotIn("a guarded change", r.stderr)
        self.assertNotIn("every commit declares its kind", r.stderr)

    def test_a_clean_message_passes_the_attribution_check_in_silence(self):
        r, _ = self.run_hook("subject\n\nbody" + KIND)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_no_argument_is_a_failure_not_a_pass(self):
        r = self.fabric.hook("commit-msg", self.repo)
        self.assertNotEqual(r.returncode, 0)


class GuardedChange(Hook):
    def test_a_hook_reached_through_a_symlink_finds_the_fabric_from_its_real_path(self):
        # core.hooksPath may name a directory of links; the owner named in authority.json proves which root the hook resolved.
        fabric = Fabric(owner_role="owner-by-file")
        self.addCleanup(fabric.cleanup)
        repo = fabric.project()
        links = os.path.join(fabric.root, "links")
        os.makedirs(links)
        for name in os.listdir(fabric.hooks):
            os.symlink(os.path.join(fabric.hooks, name), os.path.join(links, name))
        repo.stage(".agent-fabric/memory/backend-dev/workflow.md")
        fabric.bind("backend-dev")
        msg = os.path.join(fabric.root, "LINKMSG")
        with open(msg, "w", encoding="utf-8") as fh:
            fh.write("subject" + KIND)
        r = subprocess.run([os.path.join(links, "commit-msg"), msg], cwd=repo.path, capture_output=True, text=True, timeout=120, env=fabric.env())
        self.assertEqual(r.returncode, 1)
        self.assertIn("not owner-by-file", r.stderr)

    def test_an_unbound_session_is_refused_naming_no_role_and_the_owner(self):
        self.stage_guarded()
        r, after = self.run_hook("subject" + KIND)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr, "commit-msg: a guarded change, but this agent's binding holds 'no role', not fabric-coordinator.\n")
        self.assertEqual(after, "subject" + KIND)

    def test_another_role_is_refused_naming_it(self):
        self.fabric.bind("backend-dev")
        self.stage_guarded()
        r, _ = self.run_hook("subject" + KIND)
        self.assertEqual((r.returncode, r.stderr), (1, "commit-msg: a guarded change, but this agent's binding holds 'backend-dev', not fabric-coordinator.\n"))

    def test_the_owner_passes_and_the_binding_is_written_as_the_trailer_after_the_kind(self):
        self.fabric.bind("fabric-coordinator")
        self.stage_guarded()
        r, after = self.run_hook("subject\n\nbody" + KIND)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(after, "subject\n\nbody\n\nKind: work\nFabric-Role: fabric-coordinator\n")

    def test_the_change_outside_the_guarded_directory_of_a_project_is_not_guarded(self):
        self.repo.stage("src/a.txt")
        r, _ = self.run_hook("subject" + KIND)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_typed_trailer_that_differs_from_the_binding_is_refused_with_the_binding_named(self):
        self.fabric.bind("fabric-coordinator")
        self.stage_guarded()
        r, after = self.run_hook("subject" + KIND + "\nFabric-Role: backend-dev")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr, "commit-msg: the message declares Fabric-Role: backend-dev, but this agent's binding holds 'fabric-coordinator' "
                                   "— remove the line; the hook writes the binding.\n")
        self.assertTrue(after.endswith("Fabric-Role: backend-dev"))

    def test_a_typed_trailer_that_matches_is_kept_and_not_doubled_and_the_last_one_is_the_one_read(self):
        self.fabric.bind("fabric-coordinator")
        self.stage_guarded()
        r, after = self.run_hook("subject" + KIND + "\nFabric-Role: fabric-coordinator")
        self.assertEqual((r.returncode, after.count("Fabric-Role:")), (0, 1))
        r, after = self.run_hook("subject" + KIND + "\nFabric-Role: backend-dev\nFabric-Role: fabric-coordinator")
        self.assertEqual(r.returncode, 0, r.stderr)
        r, _ = self.run_hook("subject" + KIND + "\nFabric-Role: fabric-coordinator\nFabric-Role: backend-dev")
        self.assertEqual(r.returncode, 1)

    def test_the_typed_role_is_compared_exactly_case_matters_in_a_role_id(self):
        self.fabric.bind("fabric-coordinator")
        self.stage_guarded()
        r, _ = self.run_hook("subject" + KIND + "\nFabric-Role: Fabric-Coordinator")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the message declares Fabric-Role: Fabric-Coordinator, but this agent's binding holds 'fabric-coordinator'", r.stderr)

    def test_a_missing_kind_is_refused_after_the_fence_has_passed(self):
        self.fabric.bind("fabric-coordinator")
        self.stage_guarded()
        r, _ = self.run_hook("subject only")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("commit-msg: every commit declares its kind in its trailers (the last paragraph):"), r.stderr)


class OwnerRoleFromAuthority(unittest.TestCase):
    def build(self, owner="fabric-coordinator", authority_text=None):
        self.fabric = Fabric(owner_role=owner, authority_text=authority_text)
        self.addCleanup(self.fabric.cleanup)
        self.repo = self.fabric.project()
        self.repo.stage(".agent-fabric/memory/backend-dev/workflow.md")

    def attempt(self, bound):
        self.fabric.bind(bound)
        path = os.path.join(self.fabric.root, "MSG")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("subject" + KIND)
        return self.fabric.hook("commit-msg", self.repo, path)

    def test_the_owner_role_is_the_one_authority_json_names(self):
        self.build(owner="corpus-keeper")
        r = self.attempt("fabric-coordinator")
        self.assertEqual((r.returncode, r.stderr), (1, "commit-msg: a guarded change, but this agent's binding holds 'fabric-coordinator', not corpus-keeper.\n"))
        self.assertEqual(self.attempt("corpus-keeper").returncode, 0)

    def test_without_an_authority_file_or_with_one_that_cannot_be_read_the_owner_is_the_fabric_coordinator(self):
        for label, kwargs in (("missing", {"owner": None}), ("garbage", {"authority_text": "{not json"}),
                              ("no role_definitions", {"authority_text": "{}"}), ("not an object", {"authority_text": "[1]"})):
            with self.subTest(label):
                self.build(**kwargs)
                self.assertEqual(self.attempt("fabric-coordinator").returncode, 0)
                self.assertEqual(self.attempt("backend-dev").stderr,
                                 "commit-msg: a guarded change, but this agent's binding holds 'backend-dev', not fabric-coordinator.\n")


class Trailer(Hook):
    def test_a_bound_role_is_recorded_on_every_commit_not_only_a_guarded_one(self):
        self.fabric.bind("backend-dev")
        self.repo.stage("src/a.txt")
        r, after = self.run_hook("subject\n\nbody" + KIND)
        self.assertEqual((r.returncode, after), (0, "subject\n\nbody\n\nKind: work\nFabric-Role: backend-dev\n"))

    def test_no_role_held_writes_nothing(self):
        self.repo.stage("src/a.txt")
        r, after = self.run_hook("subject" + KIND)
        self.assertEqual((r.returncode, after), (0, "subject" + KIND))
        self.fabric.bind(None)
        r, after = self.run_hook("subject" + KIND)
        self.assertEqual(after, "subject" + KIND)

    def test_an_existing_fabric_role_line_in_any_case_is_left_alone(self):
        self.fabric.bind("backend-dev")
        self.repo.stage("src/a.txt")
        for line in ("fabric-role: architect-cto", "FABRIC-ROLE: architect-cto"):
            with self.subTest(line=line):
                text = "subject" + KIND + "\n" + line
                r, after = self.run_hook(text)
                self.assertEqual((r.returncode, after), (0, text))

    def test_the_kind_rule_runs_on_every_commit_and_its_refusal_is_the_hooks_exit_status(self):
        self.fabric.bind("backend-dev")
        self.repo.stage("src/a.txt")
        r, after = self.run_hook("subject without a kind")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Kind: work", r.stderr)
        self.assertEqual(after, "subject without a kind", "nothing is written to a refused message")


class DecisionRecordBodyEdit(unittest.TestCase):
    """The commit-time leg of the amendment guard (job j261): tools/fabric/adr.py staged-check, run by the repository's own copy.
    Mutations each case fails on: the staged-check call removed (refused); the MERGE_HEAD test dropped (a merge); the repository's
    own adr.py replaced by the fabric's (a project's records)."""
    RECORD = "docs/adr/ADR-001-a-rule.md"
    TEXT = ("# ADR-001 — A rule\n\n**Status:** Accepted\n\n## 1. Context\n\nThe old text.\n\n"
            "## Amendments\n\n| Date | Amendment | Effect |\n|---|---|---|\n")

    def setUp(self):
        self.fabric = Fabric(owner_role="fabric-coordinator")
        self.addCleanup(self.fabric.cleanup)
        self.fabric.bind("fabric-coordinator")
        self.repo = self.fabric.itself(files={self.RECORD: self.TEXT, "src/a.txt": "code\n"})
        self.n = 0

    def run_hook(self, text, repo=None):
        self.n += 1
        path = os.path.join(self.fabric.root, f"MSG{self.n}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return self.fabric.hook("commit-msg", repo or self.repo, path)

    def edit(self, repo=None, row=""):
        repo = repo or self.repo
        repo.write(self.RECORD, self.TEXT.replace("The old text.", "The new text.") + row)
        repo.git("add", "-A")

    def test_an_unrecorded_body_edit_is_refused_naming_the_record(self):
        self.edit()
        r = self.run_hook("reword" + KIND)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(f"adr staged-check: this commit: edits the body of {self.RECORD}", r.stderr)

    def test_the_editorial_trailer_or_a_new_amendments_row_records_it(self):
        self.edit()
        self.assertEqual(self.run_hook("reword\n\nADR-Editorial: a word, nothing decided\nKind: work").returncode, 0)
        self.edit(row="| 2026-10-18 | a rule moved | §1 says the new text |\n")
        r = self.run_hook("amend ADR-001" + KIND)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_project_without_the_fabrics_adr_tool_keeps_its_own_rules(self):
        project = self.fabric.project(files={self.RECORD: self.TEXT})
        self.edit(repo=project)
        r = self.run_hook("reword" + KIND, repo=project)
        self.assertNotIn("adr staged-check", r.stderr)

    def run_hook_as_amend(self, text):
        """The hook with a parent whose argv is `git -c … commit --amend`, as git's own is when it amends: the hook
        tells an amend from its parent's argv (commit_kind.is_amend), and a real commit would run pre-commit too."""
        self.n += 1
        path = os.path.join(self.fabric.root, f"MSG{self.n}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        hook = os.path.join(self.fabric.hooks, "commit-msg")
        return subprocess.run(["bash", "-c", 'exec -a git bash -c "$0" "$@"', '"$2" "$3"; exit $?', "commit", "--amend", hook, path],
                              cwd=self.repo.path, capture_output=True, text=True, timeout=120, env=self.fabric.env())

    def commit_quietly(self, message):
        self.repo.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", message)

    def test_an_amend_is_judged_against_the_commit_it_replaces(self):
        # Review of #297, F2: an amend replaces HEAD, so its parent is HEAD^. Kills: judging an amend against HEAD.
        row = "| 2026-10-18 | a rule moved | §1 says the new text |\n"
        self.edit(row=row)
        self.commit_quietly("amend ADR-001" + KIND)
        self.repo.write(self.RECORD, self.TEXT.replace("The old text.", "The newer text.") + row)
        self.repo.git("add", "-A")
        self.assertEqual(self.run_hook("amend ADR-001" + KIND).returncode, 1, "as a new commit on HEAD the row is not new")
        r = self.run_hook_as_amend("amend ADR-001" + KIND)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_an_amend_that_drops_the_trailer_is_refused(self):
        # Kills: running staged-check only when the index differs from HEAD (a message-only amend).
        self.edit()
        self.commit_quietly("reword\n\nADR-Editorial: a word\nKind: work")
        r = self.run_hook_as_amend("reword" + KIND)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("adr staged-check: this commit: edits the body", r.stderr)

    def test_an_amended_merge_is_not_judged_against_its_first_parent(self):
        # Review of #297, round 2, finding 2: amending a merge leaves no MERGE_HEAD; against HEAD^ it would carry the
        # other side's edits. Kills: dropping the parent count test.
        off = ("-c", "core.hooksPath=/dev/null")
        self.repo.git("checkout", "-q", "-b", "side")
        self.edit()
        self.repo.git(*off, "commit", "-qm", "reword\n\nADR-Editorial: a word\nKind: work")
        self.repo.git("checkout", "-q", "main")
        self.repo.write("src/a.txt", "more\n", append=True)
        self.repo.git("add", "-A")
        self.repo.git(*off, "commit", "-qm", "main moves\n\nKind: work")
        self.repo.git(*off, "merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")
        r = self.run_hook_as_amend("Merge branch 'side', reworded" + KIND)
        self.assertNotIn("adr staged-check", r.stderr)

    def test_a_merge_is_not_judged_again(self):
        off = ("-c", "core.hooksPath=/dev/null")
        self.repo.git("checkout", "-q", "-b", "side")
        self.edit()
        self.repo.git(*off, "commit", "-qm", "reword\n\nADR-Editorial: a word\nKind: work")
        self.repo.git("checkout", "-q", "main")
        self.repo.write("src/a.txt", "more\n", append=True)
        self.repo.git("add", "-A")
        self.repo.git(*off, "commit", "-qm", "main moves\n\nKind: work")
        self.repo.git(*off, "merge", "-q", "--no-ff", "--no-commit", "side")
        r = self.run_hook("Merge branch 'side'" + KIND)
        self.assertNotIn("adr staged-check", r.stderr)


class Carveouts(unittest.TestCase):
    def setUp(self):
        self.contributors = [{"role": "python-dev", "paths": ["tools/"], "excluding": ["tools/fabric/guards/"]}]
        self.fabric = Fabric(owner_role="fabric-coordinator", contributors=self.contributors)
        self.addCleanup(self.fabric.cleanup)
        self.repo = self.fabric.itself()
        self.n = 0

    def attempt(self, role, rel, message="subject" + KIND):
        self.fabric.bind(role)
        self.repo.stage(rel)
        self.n += 1
        path = os.path.join(self.fabric.root, f"MSG{self.n}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(message)
        r = self.fabric.hook("commit-msg", self.repo, path)
        with open(path, encoding="utf-8", newline="") as fh:
            return r, fh.read()

    def test_the_locale_holder_on_a_login_named_for_the_suffix_is_admitted_and_recorded(self):
        r, after = self.attempt("language-culture", LOCALE_FILE)
        self.assertEqual((r.returncode, r.stderr, after), (0, "", "subject" + KIND + "\nFabric-Role: language-culture\n"))

    def test_the_locale_holder_on_a_login_not_named_for_the_suffix_is_refused(self):
        r, _ = self.attempt("language-culture", "identities/roles/language-culture/locale/ge/harness.md")
        self.assertEqual((r.returncode, r.stderr), (1, "commit-msg: a guarded change, but this agent's binding holds 'language-culture', not fabric-coordinator.\n"))

    def test_the_login_may_be_the_suffix_itself(self):
        r, _ = self.attempt("language-culture", f"identities/roles/language-culture/locale/{LOGIN}/harness.md")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_another_role_on_a_locale_path_and_a_locale_beside_other_paths_are_refused(self):
        r, _ = self.attempt("backend-dev", LOCALE_FILE)
        self.assertEqual(r.returncode, 1)
        self.repo.stage("src/other.txt")
        r, _ = self.attempt("language-culture", LOCALE_FILE)
        self.assertEqual(r.returncode, 1)

    def test_a_contributor_on_its_own_branch_within_its_entry_is_admitted_and_recorded(self):
        self.repo.git("checkout", "-q", "-b", f"{HOST}/{LOGIN}/for/user/x")
        r, after = self.attempt("python-dev", "tools/fabric/x.py")
        self.assertEqual((r.returncode, r.stderr, after), (0, "", "subject" + KIND + "\nFabric-Role: python-dev\n"))

    def test_a_contributor_outside_its_entry_on_the_wrong_branch_or_unbound_is_refused_with_the_generic_line(self):
        generic = "commit-msg: a guarded change, but this agent's binding holds 'python-dev', not fabric-coordinator.\n"
        self.repo.git("checkout", "-q", "-b", f"{HOST}/{LOGIN}/for/user/x")
        r, _ = self.attempt("python-dev", "docs/x.md")                       # outside its paths
        self.assertEqual((r.returncode, r.stderr), (1, generic))
        self.repo.git("reset", "-q", "--hard")
        self.repo.git("checkout", "-q", "main")
        r, _ = self.attempt("python-dev", "tools/fabric/y.py")                # right path, not a contributor branch
        self.assertEqual((r.returncode, r.stderr), (1, generic))
        self.repo.git("reset", "-q", "--hard")
        self.repo.git("checkout", "-q", "-b", f"{HOST}/{LOGIN}/for/user/z")
        r, _ = self.attempt(None, "tools/fabric/z.py")                         # nobody bound: the contributor question is not asked
        self.assertEqual((r.returncode, r.stderr), (1, "commit-msg: a guarded change, but this agent's binding holds 'no role', not fabric-coordinator.\n"))

    def test_a_role_that_is_no_contributor_is_refused(self):
        self.repo.git("checkout", "-q", "-b", f"{HOST}/{LOGIN}/for/user/x")
        r, _ = self.attempt("devex-tooling", "tools/fabric/x.py")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
