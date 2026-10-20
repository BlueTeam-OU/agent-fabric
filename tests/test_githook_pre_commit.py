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
only when docs/adr/ is staged, on the staged tree, a moved record counted, its scratch tree removed, a project's own records left alone,
a worktree's records checked); a linked worktree of agent-fabric is agent-fabric itself for the fence, both carve-outs and the
coordinator's stamp, a project's worktree is still a project, and a git that cannot name the common directory changes neither (Worktree).
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

    def test_a_worktree_of_the_fabric_has_its_records_checked(self):
        # Mutation: _check_decision_records asks the toplevel alone, and the worktree's stale index is committed unchecked.
        wt = self.repo.worktree("feat")
        wt.stage("docs/adr/index.json", "not the generated index\n")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(wt)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("index.json: stale", r.stderr)
        self.assertEqual(os.listdir(self.scratch), [])

    def test_a_managed_projects_own_records_are_not_checked(self):
        project = self.fabric.project()
        project.stage("docs/adr/index.json", "not ours\n")
        self.fabric.bind("backend-dev")
        r = self.fabric.hook("pre-commit", project, TMPDIR=self.scratch)
        self.assertEqual((r.returncode, r.stderr), (0, ""))


class Worktree(PreCommit):
    """A linked worktree of agent-fabric, where most fabric work is committed, is agent-fabric itself: its toplevel is never the
    root, it shares the root's git common directory and inherits its hooks path (j320). Each case that admits also refuses in the
    same worktree, so a fence that judged the worktree a project's (nothing guarded but .agent-fabric/) fails it."""

    def setUp(self):
        self.build(owner_role="fabric-coordinator", contributors=[{"role": "python-dev", "paths": ["tools/"], "excluding": ["tools/fabric/guards/"]}])
        self.wt = self.fabric.itself().worktree(f"{HOST}/{LOGIN}/for/user/x")

    def test_an_unbound_session_or_another_role_staging_identities_is_refused_as_agent_fabric_itself(self):
        self.wt.stage("identities/roles/x/brief.md")
        for role in (None, "backend-dev"):
            with self.subTest(role=role):
                self.fabric.bind(role)
                r = self.run_hook(self.wt)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stderr.splitlines()[0], "pre-commit: this commit changes agent-fabric itself, which only the fabric-coordinator role writes.")
                self.assertEqual(r.stderr.splitlines()[1], "  staged: identities/roles/x/brief.md ")

    def test_the_coordinator_commits_through_git_and_is_stamped_where_another_role_is_refused(self):
        self.wt.stage("policies/x.md")
        self.fabric.bind("backend-dev")
        r = self.fabric.commit(self.wt, "x\n\nKind: work")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("this commit changes agent-fabric itself", r.stderr)
        self.fabric.bind("fabric-coordinator")
        r = self.fabric.commit(self.wt, "x\n\nKind: work")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.wt.git("log", "-1", "--format=%(trailers:key=Fabric-Role,valueonly)").stdout.strip(), "fabric-coordinator")

    def test_a_contributor_on_its_branch_is_admitted_within_its_entry_and_refused_outside_it(self):
        self.fabric.bind("python-dev")
        self.wt.stage("tools/fabric/new_thing.py")
        self.assertEqual(self.run_hook(self.wt).returncode, 0)
        self.wt.stage("identities/roles/x/brief.md")
        r = self.run_hook(self.wt)
        self.assertEqual(r.returncode, 1)
        self.assertIn("outside what python-dev commits here: identities/roles/x/brief.md", r.stderr)
        self.assertNotIn(GENERIC_TAIL, r.stderr)

    def test_the_locale_holder_is_admitted_and_another_role_on_the_same_translations_refused(self):
        self.wt.stage(f"{LOCALE}/dev-03/harness.md")
        self.fabric.bind("language-culture")
        self.assertEqual(self.run_hook(self.wt).returncode, 0)
        self.fabric.bind("backend-dev")
        r = self.run_hook(self.wt)
        self.assertEqual(r.returncode, 1)
        self.assertIn("binding holds backend-dev on login", r.stderr)

    def test_a_managed_projects_worktree_is_still_a_project(self):
        # Mutation: any repository with a git common directory taken for the fabric (`return bool(here)`).
        wt = self.fabric.project().worktree("feat")
        wt.stage("src/b.txt")
        self.fabric.bind("backend-dev")
        self.assertEqual(self.run_hook(wt).returncode, 0)
        wt.stage(".agent-fabric/memory/backend-dev/new.md")
        r = self.run_hook(wt)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr.splitlines()[0], "pre-commit: this commit changes .agent-fabric/, which only the fabric-coordinator role writes.")
        self.assertEqual(r.stderr.splitlines()[1], "  staged: .agent-fabric/memory/backend-dev/new.md ")

    def old_git(self, answer: str) -> str:
        """PATH with a `git` that cannot answer --git-common-dir: `echo` as a git older than 2.5 does (it prints an option it does
        not know and exits 0), `fail` with an error."""
        shim_dir = os.path.join(self.fabric.root, f"old-git-{answer}")
        os.makedirs(shim_dir)
        reply = 'echo "$2"; exit 0' if answer == "echo" else "exit 129"
        with open(os.path.join(shim_dir, "git"), "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\n[ "$1" = rev-parse ] && [ "$2" = --git-common-dir ] && {{ {reply}; }}\nexec /usr/bin/git "$@"\n')
        os.chmod(os.path.join(shim_dir, "git"), 0o755)
        return f"{self.fabric.stubs}:{shim_dir}:/usr/bin:/bin"

    def test_a_git_that_cannot_name_the_common_directory_reads_the_worktrees_own_layout_for_either_side(self):
        # Mutation: the layout fallback dropped (the answer taken as given): the fabric's worktree is waved through as a project.
        project = self.fabric.project().worktree("feat")
        project.stage("src/b.txt")
        self.wt.stage("identities/roles/x/brief.md")
        self.fabric.bind("backend-dev")
        for answer in ("echo", "fail"):
            with self.subTest(answer=answer):
                path = self.old_git(answer)
                r = self.fabric.hook("pre-commit", self.wt, PATH=path)
                self.assertEqual(r.returncode, 1)
                self.assertIn("this commit changes agent-fabric itself", r.stderr)
                r = self.fabric.hook("pre-commit", project, PATH=path)
                self.assertEqual((r.returncode, r.stderr), (0, ""))


class HiddenUnicode(PreCommit):
    """A staged file that is text an agent reads and hides a character (tools/fabric/hidden_unicode.py) is refused whoever commits.
    Mutations: the call to the check removed from pre_commit (every case); the check placed after the owner's return (the
    unbound and owner cases); `git show :path` read from the work tree instead (the staged-blob case); is_agent_text widened to
    every path (the .py case) or to the whole project (the project's docs case); names read without -z (the non-ASCII case); a
    merge judged against MERGE_HEAD (the merge case); a non-UTF-8 blob admitted (the not-UTF-8 case)."""

    RLO = "evil ‮ text\n"

    def setUp(self):
        self.build(owner_role="fabric-coordinator")

    def test_a_staged_md_with_a_bidi_override_is_refused_for_the_owner_and_for_an_unbound_session_alike(self):
        repo = self.fabric.itself()
        repo.stage("docs/x.md", self.RLO)
        for role in (None, "backend-dev", "fabric-coordinator"):
            with self.subTest(role=role):
                self.fabric.bind(role)
                r = self.run_hook(repo)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("docs/x.md:1:6: U+202E RIGHT-TO-LEFT OVERRIDE (bidi)", r.stderr)
                self.assertIn("tools/fabric/hidden_unicode.py", r.stderr)

    def test_a_worktree_of_the_fabric_is_judged_as_the_fabric_itself(self):
        # Mutation: _check_hidden_unicode asks the toplevel alone, and a worktree's docs/ goes unjudged as a project's.
        wt = self.fabric.itself().worktree("feat")
        wt.stage("docs/x.md", self.RLO)
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(wt)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("docs/x.md:1:6: U+202E RIGHT-TO-LEFT OVERRIDE (bidi)", r.stderr)

    def test_a_non_ascii_name_is_judged(self):
        # Mutation: names read without -z: git quotes "docs/caf\303\251.md", it ends in .md" and is skipped (review of #346, F1).
        repo = self.fabric.itself()
        repo.stage("docs/café.md", self.RLO)
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(repo)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("docs/café.md:1:6: U+202E RIGHT-TO-LEFT OVERRIDE (bidi)", r.stderr)

    def test_a_merge_is_judged_on_what_it_brings_in(self):
        # Mutation: the merge diffed against MERGE_HEAD, where the merged-in file is identical and never read (review of #346, F2).
        repo = self.fabric.itself()
        repo.git("checkout", "-q", "-b", "side")
        repo.write("docs/x.md", self.RLO)
        repo.git("add", "-A")
        repo.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "unjudged")   # a --no-verify commit, a web edit
        repo.git("checkout", "-q", "main")
        repo.write("other.md", "plain\n")
        repo.git("add", "-A")
        repo.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "main moves")
        repo.git("-c", "core.hooksPath=/dev/null", "merge", "--no-commit", "--no-ff", "-q", "side")
        for role in (None, "fabric-coordinator"):
            with self.subTest(role=role):
                self.fabric.bind(role)
                r = self.run_hook(repo)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("docs/x.md:1:6: U+202E RIGHT-TO-LEFT OVERRIDE (bidi)", r.stderr)

    def test_a_staged_file_that_is_not_utf8_is_refused(self):
        # Mutation: the UnicodeDecodeError branch admits (review of #346, F3).
        repo = self.fabric.itself()
        with open(os.path.join(repo.path, "docs.md"), "wb") as fh:
            fh.write(b"\xff\n")
        repo.git("add", "-A")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(repo)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("docs.md: not UTF-8", r.stderr)

    def test_nothing_is_committed_when_it_is_refused(self):
        repo = self.fabric.itself()
        before = repo.git("rev-parse", "HEAD").stdout
        repo.stage("docs/x.md", self.RLO)
        self.fabric.bind("fabric-coordinator")
        r = self.fabric.commit(repo, "x\n\nKind: work")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(repo.git("rev-parse", "HEAD").stdout, before)

    def test_the_staged_blob_is_judged_not_the_work_tree(self):
        repo = self.fabric.itself()
        repo.stage("docs/x.md", self.RLO)
        repo.write("docs/x.md", "clean now\n")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(repo)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("docs/x.md:1:6: U+202E", r.stderr)

    def test_the_same_character_in_a_py_file_is_admitted(self):
        repo = self.fabric.itself()
        repo.stage("tools/x.py", "# " + self.RLO)
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_json_under_identities_is_judged_and_one_elsewhere_is_not(self):
        repo = self.fabric.itself()
        self.fabric.bind("fabric-coordinator")
        repo.stage("data/x.json", '{"a": "b‮c"}\n')
        self.assertEqual(self.run_hook(repo).returncode, 0)
        repo.stage("identities/x.json", '{"a": "b‮c"}\n')
        self.assertEqual(self.run_hook(repo).returncode, 1)

    def test_in_a_managed_project_the_fabrics_directory_is_judged_and_the_projects_own_docs_are_not(self):
        project = self.fabric.project()
        self.fabric.bind("fabric-coordinator")
        project.stage("docs/x.md", self.RLO)
        r = self.run_hook(project)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        project.stage(".agent-fabric/x.md", self.RLO)
        r = self.run_hook(project)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(".agent-fabric/x.md:1:6: U+202E", r.stderr)
        self.assertNotIn("docs/x.md", r.stderr)

    def test_a_family_emoji_is_admitted(self):
        repo = self.fabric.itself()
        repo.stage("docs/x.md", "family \U0001F468‍\U0001F469‍\U0001F467\n")
        self.fabric.bind("fabric-coordinator")
        r = self.run_hook(repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
