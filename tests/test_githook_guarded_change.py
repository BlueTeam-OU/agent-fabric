#!/usr/bin/env python3
"""policies/githooks/guarded-change.sh: the library pre-commit and commit-msg SOURCE to ask "does the commit being made carry a change
of its own to what the fabric-coordinator role guards?" (Wave 9 batch 4; ADR-040 rule 5). It has no bash test of its own: this file
characterises it, function by function, the way the hooks call it (`guarded_change <fabric root>` from inside the repository, under
`set -uo pipefail`, reading `guarded_what` and `guarded` afterwards). The library is ONE constant, LIB (GITHOOKS_DIR/guarded-change.sh;
override the directory with GITHOOKS_DIR), so the same file runs against the bash today and against the Python module later (a port
that keeps the file as a sourced shim still passes; one that moves the decision must keep these answers).

What is pinned (the contract the two hooks and the CI tripwire agree on):
  scope        in agent-fabric itself (the repository's toplevel IS the fabric root, symlinks resolved) every staged path is
               guarded and the label is "agent-fabric itself"; in any other repository only .agent-fabric/ is, label ".agent-fabric/"
  filter       added, copied, deleted, modified, renamed and type-changed paths count; renames are NOT detected (a move out of a guarded
               path shows its source); nothing else is read
  empty        nothing staged: a project has no guarded path; agent-fabric itself has the one placeholder path
               "(amend or empty commit: the whole repository)", because every commit there is the coordinator's, an amend included
  merge        a merge in progress changes only what the staged tree differs by from the CLEAN three-way merge of HEAD and MERGE_HEAD
               (`git merge-tree --write-tree`): a fold of main brings landed commits and changes nothing itself, even where both sides
               moved the guarded tree; a hand edit, a conflict resolution, and keeping HEAD's guarded tree while the other side moved it
               are the merge's own change; a conflicted clean merge (merge-tree exit 1) is still the reference
  fallback     without a usable clean merge (an octopus, a git older than 2.38) the merge is judged against EVERY parent: whatever differs
               from any of them counts, listed once, sorted; so an `-s ours` octopus is not waved through
  failure      outside a git repository it does not fail: label ".agent-fabric/", nothing guarded, status 0

Mutations each case fails on (planted on the file as formatted): replacing the clean merge `git merge-tree --write-tree HEAD "$merge_head"`
by MERGE_HEAD's own tree (merge: the fold where both sides moved - it passes only when HEAD is not an ancestor of MERGE_HEAD, which is
why Merges.setUp branches the side BEFORE main moves); removing the `-- "$prefix"` scoping (scope); `--diff-filter=ACDMRT`
to `ACMRT` (filter: deletions); dropping `--no-renames` (filter: renames); removing the amend placeholder line (empty); testing only
`rc == 0` for merge-tree (merge: a conflicted merge); making the fallback judge only HEAD (fallback: octopus); `sort -u` to `sort`
(fallback: a path differing from both parents listed twice); dropping the readlink -f comparison (scope: a symlinked fabric root)."""
from __future__ import annotations

import os
import stat
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import GITHOOKS_DIR, Repo, call_library  # noqa: E402

LIB = os.path.join(GITHOOKS_DIR, "guarded-change.sh")
SCRIPT = ('guarded_change "$1"; printf "%s\\n" "$guarded_what"; for p in "${guarded[@]+"${guarded[@]}"}"; do printf "%s\\n" "$p"; done')
PLACEHOLDER = "(amend or empty commit: the whole repository)"
FILES = {"README": "r\n", ".agent-fabric/memory/m.md": "m\n", "src/a.py": "a\n"}


class Guarded(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(FILES)
        self.addCleanup(self.repo.cleanup)

    def ask(self, fabric_root=None, path="/usr/bin:/bin"):
        r = call_library(LIB, self.repo.path, SCRIPT, fabric_root or "/nonexistent-fabric-root", path=path)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        what, *paths = r.stdout.splitlines()
        return what, paths

    def side_branch(self, name="side", **files):
        """A branch off main's tip with the given files committed on it, then back on main."""
        self.repo.git("checkout", "-q", "-b", name)
        for rel, text in files.items():
            self.repo.commit(rel, text, message=f"{name}: {rel}")
        self.repo.git("checkout", "-q", "main")

    def merge_in_progress(self, *branches):
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", *branches, check=False)
        self.assertTrue(os.path.exists(os.path.join(self.repo.path, ".git", "MERGE_HEAD")), "precondition: a merge is in progress")


class Scope(Guarded):
    def test_in_a_managed_project_only_the_agent_fabric_directory_is_guarded(self):
        self.repo.stage(".agent-fabric/memory/x.md")
        self.repo.stage("src/a.py")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/x.md"]))

    def test_in_agent_fabric_itself_every_staged_path_is_guarded(self):
        self.repo.stage(".agent-fabric/memory/x.md")
        self.repo.stage("src/a.py")
        self.assertEqual(self.ask(self.repo.path), ("agent-fabric itself", [".agent-fabric/memory/x.md", "src/a.py"]))

    def test_the_fabric_root_may_be_named_through_a_symlink(self):
        link = os.path.join(self.repo.root, "fabric-link")
        os.symlink(self.repo.path, link)
        self.repo.stage("src/a.py")
        self.assertEqual(self.ask(link), ("agent-fabric itself", ["src/a.py"]))

    def test_another_repository_is_not_the_fabric(self):
        other = Repo({"x": "x\n"}, name="other")
        self.addCleanup(other.cleanup)
        self.repo.stage("src/a.py")
        self.assertEqual(self.ask(other.path), (".agent-fabric/", []))


class Filter(Guarded):
    def test_added_modified_deleted_and_type_changed_paths_count(self):
        self.repo.write(".agent-fabric/del.md", "d\n")
        self.repo.write(".agent-fabric/typed.md", "t\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-qm", "more files")
        self.repo.write(".agent-fabric/memory/m.md", "more\n", append=True)                # modified
        self.repo.write(".agent-fabric/added.md", "a\n")                                    # added
        self.repo.git("rm", "-q", ".agent-fabric/del.md")                                   # deleted
        os.remove(os.path.join(self.repo.path, ".agent-fabric/typed.md"))
        os.symlink("memory/m.md", os.path.join(self.repo.path, ".agent-fabric/typed.md"))    # type change: file -> symlink
        self.repo.git("add", "-A")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/added.md", ".agent-fabric/del.md", ".agent-fabric/memory/m.md",
                                                         ".agent-fabric/typed.md"]))

    def test_a_rename_is_a_deletion_and_an_addition_so_a_move_out_of_a_guarded_path_shows_its_source(self):
        self.repo.git("mv", ".agent-fabric/memory/m.md", "src/moved.md")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/m.md"]))
        self.assertEqual(self.ask(self.repo.path), ("agent-fabric itself", [".agent-fabric/memory/m.md", "src/moved.md"]))

    def test_a_staged_file_that_is_unchanged_from_head_is_not_a_change(self):
        self.repo.git("add", "-A")
        self.assertEqual(self.ask(), (".agent-fabric/", []))


class Empty(Guarded):
    def test_nothing_staged_in_a_project_guards_nothing(self):
        self.assertEqual(self.ask(), (".agent-fabric/", []))

    def test_nothing_staged_in_agent_fabric_itself_is_the_placeholder_because_an_amend_is_a_coordinator_commit_too(self):
        self.assertEqual(self.ask(self.repo.path), ("agent-fabric itself", [PLACEHOLDER]))

    def test_outside_a_git_repository_nothing_fails_and_nothing_is_guarded(self):
        plain = os.path.join(self.repo.root, "plain")
        os.makedirs(plain)
        r = call_library(LIB, plain, SCRIPT, plain, ceiling=self.repo.root)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, ".agent-fabric/\n", ""))


class Merges(Guarded):
    def setUp(self):
        super().setUp()
        # The side branches off the base FIRST and main moves afterwards, so HEAD is not an ancestor of MERGE_HEAD: the merge is a true
        # three-way merge in which both sides moved the guarded tree (committed the other way round it is an ancestor fold, and a merge
        # judged against MERGE_HEAD's own tree passes every case - review of #230, second engine).
        self.side_branch(**{".agent-fabric/memory/side.md": "side\n"})
        self.repo.commit(".agent-fabric/memory/main.md", "main\n", message="main moves the guarded tree")

    def test_a_clean_fold_where_both_sides_moved_the_guarded_tree_is_no_change_of_its_own(self):
        self.merge_in_progress("side")
        self.assertEqual(self.ask(), (".agent-fabric/", []))
        self.assertEqual(self.ask(self.repo.path), ("agent-fabric itself", []))

    def test_a_hand_edit_on_top_of_the_fold_is_the_merges_own_change(self):
        self.merge_in_progress("side")
        self.repo.stage(".agent-fabric/memory/main.md", "edited by hand\n")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/main.md"]))

    def test_keeping_heads_guarded_tree_while_the_other_side_moved_it_is_judged_even_though_nothing_differs_from_head(self):
        self.merge_in_progress("side")
        self.repo.git("rm", "-q", "-f", ".agent-fabric/memory/side.md")
        self.assertEqual(self.repo.git("diff", "--cached", "--name-only", "HEAD").stdout.strip(), "", "precondition: the index equals HEAD")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/side.md"]))

    def test_a_conflict_resolved_by_hand_is_judged_against_the_conflicted_clean_merge(self):
        self.repo.git("checkout", "-q", "-b", "other")
        self.repo.write(".agent-fabric/memory/c.md", "one\n")
        self.repo.write(".agent-fabric/memory/landed.md", "landed cleanly beside the conflict\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-qm", "c one")
        self.repo.git("checkout", "-q", "main")
        self.repo.write(".agent-fabric/memory/c.md", "two\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-qm", "c two")
        self.repo.git("merge", "-q", "--no-commit", "--no-ff", "other", check=False)
        self.repo.write(".agent-fabric/memory/c.md", "resolved\n")
        self.repo.git("add", "-A")
        # landed.md came in cleanly with the conflicted merge as the reference: only the resolution is the merge's own change
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/c.md"]))

    def test_a_move_made_during_a_merge_lists_both_its_source_and_its_destination(self):
        self.merge_in_progress("side")
        self.repo.git("mv", ".agent-fabric/memory/main.md", "src/moved.md")
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/main.md"]))
        self.assertEqual(self.ask(self.repo.path), ("agent-fabric itself", [".agent-fabric/memory/main.md", "src/moved.md"]))

    def test_an_octopus_is_judged_against_every_parent_so_an_ours_merge_that_drops_both_is_not_waved_through(self):
        self.side_branch("side2", **{".agent-fabric/memory/side2.md": "side2\n", "src/b.py": "b\n"})
        self.repo.git("merge", "-q", "--no-commit", "-s", "ours", "side", "side2", check=False)
        with open(os.path.join(self.repo.path, ".git", "MERGE_HEAD"), encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().split()), 2, "precondition: an octopus")
        # HEAD's tree is the staged tree. Each side branched before main moved the guarded tree: it lacks main.md and has its own file,
        # so against each parent main.md and that parent's own file differ, listed once between them
        self.assertEqual(self.ask(), (".agent-fabric/", [".agent-fabric/memory/main.md", ".agent-fabric/memory/side.md",
                                                           ".agent-fabric/memory/side2.md"]))
        what, paths = self.ask(self.repo.path)
        self.assertEqual((what, "src/b.py" in paths), ("agent-fabric itself", True))

    def test_a_path_that_differs_from_both_parents_is_listed_once(self):
        self.side_branch("side2", **{".agent-fabric/memory/side2.md": "side2\n"})
        self.repo.git("merge", "-q", "--no-commit", "-s", "ours", "side", "side2", check=False)
        self.repo.stage(".agent-fabric/memory/main.md", "edited in the octopus\n")
        self.repo.stage(".agent-fabric/memory/side.md", "side differs from the octopus\n")
        _, paths = self.ask()
        self.assertEqual(len(paths), len(set(paths)), paths)
        self.assertEqual(paths, sorted(paths))

    def test_without_merge_tree_write_tree_a_fold_is_judged_against_every_parent_and_lists_what_the_other_side_brought(self):
        shim_dir = os.path.join(self.repo.root, "shim")
        os.makedirs(shim_dir)
        shim = os.path.join(shim_dir, "git")
        with open(shim, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\n[ "$1" = merge-tree ] && exit 129\nexec /usr/bin/git "$@"\n')
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR)
        self.merge_in_progress("side")
        # a git older than 2.38 has no `merge-tree --write-tree`: the clean merge is unavailable, every parent is the reference
        # the fold result differs from HEAD by what the side brought (side.md) and from the side by what main brought (main.md)
        self.assertEqual(self.ask(path=f"{shim_dir}:/usr/bin:/bin"), (".agent-fabric/", [".agent-fabric/memory/main.md", ".agent-fabric/memory/side.md"]))


if __name__ == "__main__":
    unittest.main()
