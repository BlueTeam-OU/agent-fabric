#!/usr/bin/env python3
"""policies/githooks/pre-commit: refuses a commit that stages anything the fabric-coordinator role guards (everything in agent-fabric
itself, `.agent-fabric/` in a managed project) unless the live binding holds the owning role or a carve-out admits it (Wave 9 batch 4;
ADR-040 rule 5). It has no bash test of its own; tests/test_githooks_cli.py drives it through `git commit` and pins the fence, the amend,
the fold of main, the locale carve-out's merge and the decision-record check. This file adds what that one does not pin, driving the hook
as git does - by path, from the repository, no arguments, the staged index as its input - so it runs unchanged against the bash today and
against the Python module later. The seam is ONE constant, githook_fixtures.GITHOOKS_DIR (the directory under test, default policies/githooks; the GITHOOKS_DIR environment variable overrides it), and the hook is its pre-commit file. The fabric
under test is a scratch root with a COPY of the hooks, its own policies/authority.json and links to the real runtime/ and tools/
(githook_fixtures.Fabric); the binding is a file in a scratch state directory.

Carried here (each is a method): nothing guarded staged is exit 0 and silence, whoever is bound; the owner role READ from authority.json and
defaulting to fabric-coordinator when the file is missing or unreadable; the refusal's exact first line, its staged list (the first eight
paths, then "... (N paths)") and its binding line ("(no role bound)" when none); the label "agent-fabric itself" and the placeholder path of
an empty commit there; the locale carve-out's own refusal text (role, suffix, login named) and the login test (a suffix matched by the end of
the login or by the whole login); the contributor carve-out's three exits (0 admits in silence, 1 refuses with the module's reason and not the
generic block, anything else falls to the generic refusal) and that it exists in agent-fabric itself only; a hook reached through a link
finds the fabric from its real path (Linked); the decision-records leg in agent-fabric itself (DecisionRecords: judged before the role,
only when docs/adr/ is staged, on the staged tree, a moved record counted, its scratch tree removed, a project's own records left alone).
test_githooks_cli.py holds the leg's end-to-end cases; DecisionRecords adds the ones that need the hook run alone.

Mutations each case fails on (planted on the hook as formatted): `(( ${#staged[@]} )) || exit 0` removed (silence); the owner role
read from a constant (authority.json); `:0:8` to `:0:3` (the staged list); `held` forced to the owner (the binding line and every
refusal); the `what` label swapped (itself); the locale test's `*-"$locale_suffix"` dropped (login test); `case $?` mapping 1 to the
generic refusal (contributor refusals); the carve-out run in managed projects too (agent-fabric itself only); the inner `readlink -f`
dropped from `FABRIC_ROOT=` (Linked); the records leg's condition set to `&& false` / `&& true` (DecisionRecords: inconsistent refused /
unstaged not checked), made to wait for the owner role (whoever is bound), `--diff-filter=AM` added (moved record), `checkout-index`
replaced by a copy of the working tree (staged tree), either `rm -rf "$adr_tree"` dropped (scratch tree), the toplevel test inverted
(managed project)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import HOST, LOGIN, ROOT, Fabric  # noqa: E402
from instance_fixtures import write_registry  # noqa: E402

GENERIC_TAIL = "agent-fabric is read-only for every role but fabric-coordinator; in a managed\nproject, .agent-fabric/ is."
LOCALE = "identities/roles/language-culture/locale"


class PreCommit(unittest.TestCase):
    owner = "fabric-coordinator"

    def build(self, **kwargs):
        self.fabric = Fabric(**kwargs)
        self.addCleanup(self.fabric.cleanup)

    def run_hook(self, repo):
        return self.fabric.hook("pre-commit", repo)


class Project(PreCommit):
    def setUp(self):
        self.build(owner_role="fabric-coordinator")
        self.repo = self.fabric.project()

    def test_nothing_guarded_staged_is_exit_0_and_silence_whoever_is_bound(self):
        self.repo.stage("src/a.txt")
        for role in (None, "backend-dev", "fabric-coordinator"):
            with self.subTest(role=role):
                self.fabric.bind(role)
                r = self.run_hook(self.repo)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_nothing_staged_at_all_in_a_project_is_exit_0(self):
        self.assertEqual(self.run_hook(self.repo).returncode, 0)

    def test_the_owner_may_stage_the_guarded_directory(self):
        self.fabric.bind("fabric-coordinator")
        self.repo.stage(".agent-fabric/memory/backend-dev/new.md")
        r = self.run_hook(self.repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_the_refusal_has_its_first_line_its_staged_list_and_its_binding_line(self):
        self.repo.stage(".agent-fabric/memory/backend-dev/new.md")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        lines = r.stderr.splitlines()
        self.assertEqual(lines[0], "pre-commit: this commit changes .agent-fabric/, which only the fabric-coordinator role writes.")
        self.assertEqual(lines[1], "  staged: .agent-fabric/memory/backend-dev/new.md ")
        self.assertEqual(lines[2], "  this agent's binding holds: (no role bound)")
        self.assertEqual(lines[3], "")
        self.assertIn(GENERIC_TAIL, r.stderr)
        self.assertIn("bin/fabric-role bind fabric-coordinator", r.stderr)
        self.assertTrue(r.stderr.rstrip().endswith("See agent-fabric policies/AUTHORITY.md."))
        self.assertEqual(r.stdout, "")

    def test_the_binding_line_names_the_held_role(self):
        self.fabric.bind("backend-dev")
        self.repo.stage(".agent-fabric/memory/backend-dev/new.md")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("  this agent's binding holds: backend-dev\n", r.stderr)

    def test_the_staged_list_shows_eight_paths_and_counts_the_rest(self):
        for i in range(11):
            self.repo.stage(f".agent-fabric/memory/backend-dev/f{i:02d}.md")
        r = self.run_hook(self.repo)
        staged = [ln for ln in r.stderr.splitlines() if ln.startswith("  staged: ")][0]
        shown = staged[len("  staged: "):].split()
        self.assertEqual(shown[:8], [f".agent-fabric/memory/backend-dev/f{i:02d}.md" for i in range(8)])
        self.assertEqual(shown[8:], ["…", "(11", "paths)"])

    def test_exactly_eight_paths_carry_no_count(self):
        for i in range(8):
            self.repo.stage(f".agent-fabric/memory/backend-dev/f{i}.md")
        r = self.run_hook(self.repo)
        staged = [ln for ln in r.stderr.splitlines() if ln.startswith("  staged: ")][0]
        self.assertNotIn("paths)", staged)

    def test_the_contributor_carve_out_is_agent_fabric_itself_only(self):
        contributors = [{"role": "python-dev", "paths": [".agent-fabric/"], "excluding": []}]
        fabric = Fabric(owner_role="fabric-coordinator", contributors=contributors)
        self.addCleanup(fabric.cleanup)
        # contributors.py reads the REPOSITORY's committed policies/authority.json: the project carries one that would admit the commit
        authority = json.dumps({"role_definitions": {"role": "fabric-coordinator", "holders": []}, "contributors": contributors})
        repo = fabric.project(files={"src/a.txt": "code\n", ".agent-fabric/memory/backend-dev/workflow.md": "slice\n", "policies/authority.json": authority})
        fabric.bind("python-dev")
        repo.git("checkout", "-q", "-b", f"{HOST}/{LOGIN}/for/user/x")
        repo.stage(".agent-fabric/memory/backend-dev/new.md")
        r = fabric.hook("pre-commit", repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn(GENERIC_TAIL, r.stderr)


class OwnerRole(PreCommit):
    def attempt(self, bound):
        self.fabric.bind(bound)
        return self.run_hook(self.repo)

    def stage_for(self, **kwargs):
        self.build(**kwargs)
        self.repo = self.fabric.project()
        self.repo.stage(".agent-fabric/memory/backend-dev/new.md")

    def test_the_owner_is_the_role_authority_json_names(self):
        self.stage_for(owner_role="corpus-keeper")
        r = self.attempt("fabric-coordinator")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("pre-commit: this commit changes .agent-fabric/, which only the corpus-keeper role writes.\n"))
        self.assertIn("bin/fabric-role bind corpus-keeper", r.stderr)
        self.assertEqual(self.attempt("corpus-keeper").returncode, 0)

    def test_without_an_authority_file_or_with_one_that_cannot_be_read_it_is_the_fabric_coordinator(self):
        for label, kwargs in (("missing", {"owner_role": None}), ("garbage", {"authority_text": "{nope"}), ("no role_definitions", {"authority_text": "{}"}),
                              ("a list", {"authority_text": "[1]"})):
            with self.subTest(label):
                self.stage_for(**kwargs)
                self.assertEqual(self.attempt("fabric-coordinator").returncode, 0)
                r = self.attempt("backend-dev")
                self.assertEqual(r.returncode, 1)
                self.assertIn("only the fabric-coordinator role writes", r.stderr)


class AgentFabricItself(PreCommit):
    def setUp(self):
        self.build(owner_role="fabric-coordinator", contributors=[{"role": "python-dev", "paths": ["tools/"], "excluding": ["tools/fabric/guards/"]}])
        self.repo = self.fabric.itself()

    def test_every_staged_path_is_guarded_and_the_label_says_so(self):
        self.repo.stage("src/b.txt")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[0], "pre-commit: this commit changes agent-fabric itself, which only the fabric-coordinator role writes.")
        self.assertEqual(r.stderr.splitlines()[1], "  staged: src/b.txt ")
        self.fabric.bind("fabric-coordinator")
        self.assertEqual(self.run_hook(self.repo).returncode, 0)

    def test_nothing_staged_is_the_placeholder_because_an_amend_is_a_coordinator_commit(self):
        self.fabric.bind("backend-dev")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[1], "  staged: (amend or empty commit: the whole repository) ")
        self.fabric.bind("fabric-coordinator")
        self.assertEqual(self.run_hook(self.repo).returncode, 0)

    def test_the_locale_holder_on_a_login_named_for_the_suffix_is_admitted_in_silence(self):
        self.fabric.bind("language-culture")
        self.repo.stage(f"{LOCALE}/dev-03/harness.md")                        # the stand-in login stub-dev-03 ends in -dev-03
        r = self.run_hook(self.repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_the_login_may_be_the_suffix_itself(self):
        self.fabric.bind("language-culture")
        self.repo.stage(f"{LOCALE}/{LOGIN}/harness.md")
        self.assertEqual(self.run_hook(self.repo).returncode, 0)

    def test_the_locale_refusal_names_the_role_the_suffix_and_the_login(self):
        self.fabric.bind("language-culture")
        self.repo.stage(f"{LOCALE}/ge/harness.md")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr, "pre-commit: this commit changes only language-culture's locale/ge/ translations,\n"
                                   "  which the holder of language-culture named for ge may commit — this session's\n"
                                   f"  binding holds language-culture on login {LOGIN}.\n")

    def test_the_locale_refusal_for_another_role_and_for_nobody(self):
        self.repo.stage(f"{LOCALE}/dev-03/harness.md")
        self.fabric.bind("backend-dev")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("binding holds backend-dev on login", r.stderr)
        self.fabric.unbind()
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("binding holds (no role bound) on login", r.stderr)

    def test_a_locale_file_beside_any_other_path_is_the_generic_refusal(self):
        self.fabric.bind("language-culture")
        self.repo.stage(f"{LOCALE}/dev-03/harness.md")
        self.repo.stage("src/b.txt")
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn(GENERIC_TAIL, r.stderr)

    def contributor(self, role, rel, branch=None):
        self.fabric.bind(role)
        self.repo.git("checkout", "-q", "-b", branch or f"{HOST}/{LOGIN}/for/user/x")
        self.repo.stage(rel)
        return self.run_hook(self.repo)

    def test_a_contributor_within_its_entry_on_its_branch_is_admitted_in_silence(self):
        r = self.contributor("python-dev", "tools/fabric/new_thing.py")
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_contributor_outside_its_entry_is_refused_with_the_modules_reason_not_the_generic_block(self):
        r = self.contributor("python-dev", "docs/x.md")
        self.assertEqual(r.returncode, 1)
        self.assertNotEqual(r.stderr, "")
        self.assertNotIn(GENERIC_TAIL, r.stderr)

    def test_a_contributor_on_the_wrong_branch_is_refused_with_the_modules_reason(self):
        r = self.contributor("python-dev", "tools/fabric/new_thing.py", branch="feature/x")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(GENERIC_TAIL, r.stderr)

    def test_a_role_that_is_no_contributor_falls_to_the_generic_refusal(self):
        r = self.contributor("devex-tooling", "tools/fabric/new_thing.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn(GENERIC_TAIL, r.stderr)

    def test_an_unbound_session_is_refused_generically_the_contributor_question_is_not_asked(self):
        r = self.contributor(None, "tools/fabric/new_thing.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("this agent's binding holds: (no role bound)", r.stderr)


class Linked(PreCommit):
    def test_a_hook_reached_through_a_symlink_finds_the_fabric_from_its_real_path(self):
        # core.hooksPath may name a directory of links; the owner read from authority.json proves which root the hook resolved.
        self.build(owner_role="owner-by-file")
        repo = self.fabric.project()
        links = os.path.join(self.fabric.root, "links")
        os.makedirs(links)
        for name in os.listdir(self.fabric.hooks):
            os.symlink(os.path.join(self.fabric.hooks, name), os.path.join(links, name))
        repo.stage(".agent-fabric/memory/backend-dev/new.md")
        self.fabric.bind("backend-dev")
        r = self.fabric.hook("pre-commit", repo)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[0], "pre-commit: this commit changes .agent-fabric/, which only the owner-by-file role writes.")
        r = subprocess.run([os.path.join(links, "pre-commit")], cwd=repo.path, capture_output=True, text=True, timeout=120, env=self.fabric.env())
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[0], "pre-commit: this commit changes .agent-fabric/, which only the owner-by-file role writes.")


class DecisionRecords(PreCommit):
    """The decision records keep their own books in agent-fabric itself (the hook's first leg, before the role is asked)."""

    def setUp(self):
        self.build(owner_role="fabric-coordinator")
        self.repo = self.fabric.itself()
        self.scratch = os.path.join(self.fabric.root, "tmp")
        os.makedirs(self.scratch)
        f = self.fabric.fabric
        shutil.copytree(os.path.join(ROOT, "tests", "fixtures", "adr-mini", "docs", "adr"), os.path.join(f, "docs", "adr"))
        os.makedirs(os.path.join(f, "docs", "live-checks"))
        write_registry(os.path.join(f, "projects"))
        self.repo.git("add", "-A")
        self.repo.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "records in place")

    def run_hook(self, repo=None):
        return self.fabric.hook("pre-commit", repo or self.repo, TMPDIR=self.scratch)

    def stale_index(self):
        self.repo.stage("docs/adr/index.json", "not the generated index\n")

    def test_an_inconsistent_change_is_refused_naming_the_fault_whoever_is_bound(self):
        self.stale_index()
        for role in ("fabric-coordinator", "backend-dev", None):
            with self.subTest(role=role):
                self.fabric.bind(role)
                r = self.run_hook()
                self.assertEqual(r.returncode, 1)
                self.assertEqual(r.stderr.splitlines()[0], "pre-commit: the decision records in this commit are not consistent \u2014 not committed:")
                self.assertIn("index.json: stale", r.stderr)
                self.assertNotIn("only the fabric-coordinator role writes", r.stderr)

    def test_a_consistent_change_goes_on_to_the_role_question(self):
        self.repo.stage("docs/adr/DIGEST.md", "a note\n")
        self.fabric.bind("backend-dev")
        r = self.run_hook()
        self.assertEqual(r.returncode, 1)
        self.assertIn("this commit changes agent-fabric itself, which only the fabric-coordinator role writes.", r.stderr)
        self.fabric.bind("fabric-coordinator")
        self.assertEqual(self.run_hook().returncode, 0)

    def test_a_commit_that_stages_no_record_is_not_checked(self):
        # HEAD already holds inconsistent records, so a check run on this commit would refuse it: a passing check is silent.
        self.repo.stage("docs/adr/index.json", "not the generated index\n")
        self.repo.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "records gone stale")
        self.repo.stage("src/b.txt")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_record_moved_out_of_the_directory_is_a_change_to_it(self):
        self.repo.git("mv", "docs/adr/DIGEST.md", "docs/DIGEST.md")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not consistent", r.stderr)

    def test_the_scratch_tree_is_removed_whether_the_records_pass_or_not(self):
        self.fabric.bind("fabric-coordinator")
        self.repo.stage("docs/adr/DIGEST.md", "a note\n")
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertEqual(os.listdir(self.scratch), [])
        self.stale_index()
        self.assertEqual(self.run_hook().returncode, 1)
        self.assertEqual(os.listdir(self.scratch), [])

    def test_the_staged_tree_is_checked_not_the_working_tree(self):
        self.repo.stage("docs/adr/index.json", "not the generated index\n")
        with open(os.path.join(self.repo.path, "docs", "adr", "index.json"), "w", encoding="utf-8") as fh:
            fh.write(self.repo.git("show", "HEAD:docs/adr/index.json").stdout)
        self.fabric.bind("fabric-coordinator")
        self.assertEqual(self.run_hook().returncode, 1)

    def test_a_managed_projects_own_records_are_not_checked(self):
        project = self.fabric.project()
        project.stage("docs/adr/index.json", "not ours\n")
        self.fabric.bind("backend-dev")
        r = self.fabric.hook("pre-commit", project, TMPDIR=self.scratch)
        self.assertEqual((r.returncode, r.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
