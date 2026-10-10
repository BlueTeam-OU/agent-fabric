#!/usr/bin/env python3
"""tools/fabric/memory_check.py (bin/fabric-memory-check): a curated slice's
cited paths, checked against the tree they belong to. Every case builds its
own corpus and tree in a scratch directory and runs the real command line
with a minimal environment; nothing reads the checkout's memory/."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import memory_check  # noqa: E402

TOOL = os.path.join(HERE, "tools", "fabric", "memory_check.py")
BIN = os.path.join(HERE, "bin", "fabric-memory-check")
FRONT = '---\nrole: "r"\nclass: {klass}\ntopic: "t"\n{origin}---\n\n'


def slice_text(*sections: tuple[str, str], klass: str = "domain", origins: tuple[tuple[str, str], ...] = ()) -> str:
    origin = "origin:\n" + "".join(f'  - project: "{p}"\n    working_copy: "{w}"\n' for p, w in origins) if origins else ""
    return FRONT.format(klass=klass, origin=origin) + "\n".join(f"## {h}\n\n{b}\n" for h, b in sections)


class Tree(unittest.TestCase):
    """A fabric-shaped checkout: tools/, docs/, a memory/ corpus, and a sibling."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="memcheck-")
        self.addCleanup(shutil.rmtree, self.base, True)
        self.tree = os.path.join(self.base, "agent-fabric")
        self.corpus = os.path.join(self.tree, "memory")
        for rel in ("tools/fabric/layout.py", "docs/adr/ADR-001.md", "runtime/x.sh"):
            self.write(rel, "x\n")
        os.makedirs(os.path.join(self.corpus, "domains", "d", "domain"))

    def write(self, rel, text, root=None):
        path = os.path.join(root or self.tree, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def slice(self, name, *sections, klass="domain", origins=()):
        return self.write(f"memory/domains/d/domain/{name}.md", slice_text(*sections, klass=klass, origins=origins))

    def run_cli(self, *args, entry=None, env=None):
        e = {"PATH": "/usr/bin:/bin", **(env or {})}
        argv = [entry or sys.executable, *([] if entry else [TOOL]), *args]
        return subprocess.run(argv, capture_output=True, text=True, env=e, timeout=60, stdin=subprocess.DEVNULL, check=False)

    def report(self, *args):
        r = self.run_cli(self.corpus, "--json", *args)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r)
        return json.loads(r.stdout)

    def verdicts(self, *args):
        return {(s["slice"].rsplit("/", 1)[-1], s["heading"]): s["verdict"] for s in self.report(*args)["sections"]}


class Verdicts(Tree):
    def test_a_gone_path_is_stale_hard_an_existing_one_fresh_no_path_no_anchor(self):
        self.slice("a", ("gone", "see `tools/fabric/deleted.py`"), ("here", "see `tools/fabric/layout.py` and docs/adr/ADR-001.md"),
                   ("prose", "nothing cited, only prose"))
        self.assertEqual(self.verdicts(), {("a.md", "gone"): "stale-hard", ("a.md", "here"): "fresh", ("a.md", "prose"): "no-anchor"})

    def test_a_section_is_stale_if_any_of_its_paths_is_gone(self):
        self.slice("a", ("mixed", "`tools/fabric/layout.py` then `tools/fabric/deleted.py`"))
        (s,) = self.report()["sections"]
        self.assertEqual((s["verdict"], [(p["path"], p["status"]) for p in s["paths"]]),
                         ("stale-hard", [("tools/fabric/layout.py", "exists"), ("tools/fabric/deleted.py", "stale-hard")]))

    def test_a_sibling_path_is_checked_where_the_checkout_is_beside_the_tree_else_unchecked(self):
        self.slice("a", ("absent", "`../agent-gateway/src/main.rs`"), ("present", "`../other/src/lib.rs` and `../other/src/gone.rs`"),
                   ("fine", "`../other/src/lib.rs`"))
        self.write("src/lib.rs", "x", root=os.path.join(self.base, "other"))
        self.assertEqual(self.verdicts(), {("a.md", "absent"): "unchecked", ("a.md", "present"): "stale-hard", ("a.md", "fine"): "fresh"})

    def test_unchecked_never_masks_a_stale_path_and_never_counts_as_stale(self):
        self.slice("a", ("both", "`../none/x/y` and `tools/fabric/deleted.py`"), ("only", "`../none/x/y`"))
        self.assertEqual(self.verdicts(), {("a.md", "both"): "stale-hard", ("a.md", "only"): "unchecked"})
        self.assertEqual(self.report()["counts"]["stale-hard"], 1)

    def test_each_section_of_each_slice_is_its_own_row_and_a_path_cited_twice_is_listed_once(self):
        self.slice("a", ("one", "`tools/fabric/deleted.py` and again tools/fabric/deleted.py"), ("two", "`tools/fabric/deleted.py`"))
        self.slice("b", ("one", "`tools/fabric/layout.py`"))
        rows = self.report()["sections"]
        self.assertEqual([(r["slice"].rsplit("/", 1)[-1], r["heading"], len(r["paths"])) for r in rows], [("a.md", "one", 1), ("a.md", "two", 1), ("b.md", "one", 1)])


class Origins(Tree):
    """A slice's paths belong to the project it came from, which is not always the tree it is kept in."""

    def test_a_path_of_another_origin_project_without_its_checkout_is_unchecked_never_stale(self):
        self.slice("a", ("s", "`tools/checks/gzapp_only.sh`"), origins=(("gzapp", "gzapp"),))
        (row,) = self.report()["sections"]
        self.assertEqual(row["verdict"], "unchecked")
        self.assertEqual(row["paths"], [{"path": "tools/checks/gzapp_only.sh", "status": "unchecked",
                                          "why": "origin gzapp: no checkout 'gzapp' beside the tree"}])

    def test_with_the_origin_checkout_beside_the_tree_the_path_is_judged_there(self):
        self.write("tools/checks/here.sh", "x", root=os.path.join(self.base, "gzapp"))
        self.slice("a", ("present", "`tools/checks/here.sh`"), ("gone", "`tools/checks/gone.sh`"), origins=(("gzapp", "gzapp"),))
        self.assertEqual(self.verdicts(), {("a.md", "present"): "fresh", ("a.md", "gone"): "stale-hard"})

    def test_the_trees_own_project_is_the_tree_whatever_its_directory_is_called(self):
        self.slice("a", ("s", "`tools/fabric/deleted.py`"), origins=(("agent-fabric", "fabric-na"),))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "stale-hard"})

    def test_a_path_that_exists_in_the_corpus_tree_exists_whatever_the_origin(self):
        self.slice("a", ("s", "`tools/fabric/layout.py`"), origins=(("gzapp", "gzapp"),))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "fresh"})

    def test_with_two_origins_one_missing_a_path_found_in_neither_here_is_unchecked(self):
        self.write("tools/x.sh", "x", root=os.path.join(self.base, "gzapp"))
        self.slice("a", ("s", "`tools/x.sh` and `tools/fabric/deleted.py`"), origins=(("agent-fabric", "agent-fabric"), ("interweave", "InterWeave")))
        (row,) = self.report()["sections"]
        self.assertEqual([(p["path"], p["status"]) for p in row["paths"]], [("tools/x.sh", "unchecked"), ("tools/fabric/deleted.py", "unchecked")])

    def test_a_working_copys_corpus_takes_every_origin_for_its_own_tree(self):
        wc = os.path.join(self.base, "proj")
        self.write("src/app.rs", "x", root=wc)
        self.write(".agent-fabric/memory/r/solution/s.md", slice_text(("s", "`src/gone.rs`"), klass="solution", origins=(("whatever", "proj"),)), root=wc)
        doc = json.loads(self.run_cli(os.path.join(wc, ".agent-fabric", "memory"), "--json").stdout)
        self.assertEqual(doc["sections"][0]["verdict"], "stale-hard")

    def test_project_names_the_trees_own_project_when_the_layout_does_not(self):
        self.slice("a", ("s", "`tools/fabric/deleted.py`"), origins=(("gzapp", "gzapp"),))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "unchecked"})
        self.assertEqual(self.verdicts("--project", "gzapp"), {("a.md", "s"): "stale-hard"})

    def test_an_origin_with_no_working_copy_says_so_not_none(self):
        self.write("memory/domains/d/domain/c.md", "---\nclass: domain\norigin:\n  - project: \"gzapp\"\n---\n\n## s\n\n`tools/gone.ts`\n")
        (row,) = self.report()["sections"]
        self.assertEqual(row["paths"][0]["why"], "origin gzapp: names no working_copy to look in")

    def test_an_origin_checkout_that_goes_unreadable_after_it_was_found_is_unknown_never_stale(self):
        from unittest import mock
        self.write("tools/web/app.ts", "x", root=os.path.join(self.base, "gzapp"))
        self.slice("a", ("s", "`tools/web/app.ts` and `tools/fabric/deleted.py`"), origins=(("gzapp", "gzapp"),))
        (row,) = self.report()["sections"]
        self.assertEqual({p["path"]: p["status"] for p in row["paths"]}, {"tools/web/app.ts": "exists", "tools/fabric/deleted.py": "stale-hard"},
                         "while the checkout can be read: the file is there, the other is gone from both")
        sib = os.path.join(self.base, "gzapp")
        os.chmod(sib, 0)
        self.addCleanup(os.chmod, sib, 0o755)
        if os.geteuid() == 0:
            self.skipTest("a root user lists everything")
        with mock.patch.object(memory_check, "readable_dir", lambda p: True):      # the race: found readable, then not
            rows = memory_check.check(self.corpus, self.tree)
        (row,) = rows
        self.assertEqual(row["verdict"], "unchecked")
        self.assertEqual({p["path"]: p["status"] for p in row["paths"]}, {"tools/web/app.ts": "unchecked", "tools/fabric/deleted.py": "unchecked"})
        self.assertEqual(row["paths"][0]["why"], "origin checkout 'gzapp': cannot read it")

    def test_a_working_copy_name_that_climbs_is_no_checkout_even_where_it_would_reach_one(self):
        self.write("tools/x.sh", "x", root=os.path.join(self.base, "gzapp"))
        climbing = f"../{os.path.basename(self.base)}/gzapp"      # from beside the tree, it reaches base/gzapp
        self.slice("a", ("s", "`tools/x.sh`"), origins=(("gzapp", climbing),))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "unchecked"})

    def test_a_citation_is_recognised_by_any_tree_the_slice_may_belong_to(self):
        os.makedirs(os.path.join(self.base, "gzapp", "apps"))
        self.slice("a", ("s", "`apps/web/gone.ts`"), origins=(("gzapp", "gzapp"),))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "stale-hard"})


class Unreadable(Tree):
    def setUp(self):
        super().setUp()
        if os.geteuid() == 0:
            self.skipTest("a root user reads everything")

    def chmod(self, path, mode):
        os.chmod(path, mode)
        self.addCleanup(os.chmod, path, 0o755 if os.path.isdir(path) else 0o644)

    def test_an_unreadable_corpus_root_is_a_refusal_not_a_clean_report(self):
        self.chmod(self.corpus, 0)
        r = self.run_cli(self.corpus)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertTrue(r.stderr.startswith("fabric-memory-check: cannot read the corpus"), r.stderr)

    def test_an_unreadable_directory_is_a_row_and_the_rest_is_still_reported(self):
        self.slice("a", ("s", "`tools/fabric/deleted.py`"))
        locked = os.path.join(self.corpus, "domains", "locked")
        os.makedirs(locked)
        self.chmod(locked, 0)
        doc = self.report()
        self.assertEqual({r["verdict"] for r in doc["sections"]}, {"stale-hard", "unreadable"})
        (bad,) = [r for r in doc["sections"] if r["verdict"] == "unreadable"]
        self.assertEqual((bad["slice"], bad["paths"]), ("domains/locked", []))
        self.assertIn("cannot read the directory", bad["why"])
        self.assertEqual(doc["counts"]["unreadable"], 1)

    def test_an_unreadable_slice_and_a_slice_that_is_not_utf8_are_rows_not_tracebacks(self):
        locked = self.slice("locked", ("s", "x"))
        self.chmod(locked, 0)
        broken = self.slice("broken", ("s", "x"))
        with open(broken, "ab") as fh:
            fh.write(b"\xff\xfe")
        self.slice("ok", ("s", "`tools/fabric/layout.py`"))
        r = self.run_cli(self.corpus)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(sorted(ln.split("\t")[1] for ln in r.stdout.splitlines() if ln.startswith("unreadable")),
                         ["domains/d/domain/broken.md", "domains/d/domain/locked.md"])
        self.assertIn("1 fresh", r.stdout.splitlines()[-1])

    def test_a_dangling_link_in_the_corpus_is_a_row_not_a_silent_skip(self):
        os.symlink(os.path.join(self.base, "nowhere.md"), os.path.join(self.corpus, "domains", "d", "domain", "dangling.md"))
        (row,) = self.report()["sections"]
        self.assertEqual((row["verdict"], row["slice"], row["why"]), ("unreadable", "domains/d/domain/dangling.md", "cannot read it: No such file or directory"))

    def test_a_sibling_checkout_that_exists_but_cannot_be_read_is_unchecked(self):
        sib = os.path.join(self.base, "sib")
        self.write("src/a.rs", "x", root=sib)
        self.chmod(sib, 0)
        self.slice("a", ("s", "`../sib/src/a.rs`"))
        self.assertEqual(self.verdicts(), {("a.md", "s"): "unchecked"})


class Recognition(Tree):
    def paths(self, text):
        self.slice("a", ("s", text))
        (s,) = self.report()["sections"]
        return [p["path"] for p in s["paths"]]

    def test_patterns_placeholders_urls_absolute_paths_and_word_pairs_are_not_citations(self):
        text = ("runtime/*.mjs and tests/test_<x>.py and tools/{a,b}.py and docs/$X/y and tools/fabric/[ab].py "
                "https://example.com/tools/fabric/layout.py /home/u/tools/fabric/deleted.py ~/tools/fabric/deleted.py "
                "HELLO/GOODBYE P1/P2 origin/main and/or")
        self.assertEqual(self.paths(text), [])

    def test_a_line_suffix_a_trailing_slash_and_sentence_punctuation_are_dropped(self):
        self.assertEqual(self.paths("`tools/fabric/layout.py:120`, then docs/adr/. And (runtime/x.sh), also tools/fabric/layout.py:12:3."),
                         ["tools/fabric/layout.py", "docs/adr", "runtime/x.sh"])

    def test_a_dot_slash_is_dropped_and_a_trailing_dash_is_punctuation(self):
        self.assertEqual(self.paths("`./tools/fabric/layout.py` and tools/fabric/layout.py- then ./docs/adr/ADR-001.md"),
                         ["tools/fabric/layout.py", "docs/adr/ADR-001.md"])

    def test_a_fenced_block_counts_like_prose(self):
        self.assertEqual(self.paths("```sh\nbash runtime/x.sh --go\n```"), ["runtime/x.sh"])

    def test_only_a_top_level_directory_the_tree_has_makes_a_path_unless_named(self):
        self.assertEqual(self.paths("`vanished/dir/x.py`"), [])
        self.assertEqual(self.report("--known-dir", "vanished")["sections"][0]["paths"], [{"path": "vanished/dir/x.py", "status": "stale-hard"}])

    def test_a_dot_directory_of_the_tree_is_a_top_level_directory(self):
        self.write(".agent-fabric/roles/r.md", "x")
        self.assertEqual(self.paths("`.agent-fabric/roles/r.md` and `.agent-fabric/roles/gone.md`"),
                         [".agent-fabric/roles/r.md", ".agent-fabric/roles/gone.md"])

    def test_a_double_dot_path_is_only_ever_a_sibling_one_directory_up(self):
        self.assertEqual(self.paths("`../../x/y/z` and `../a/b` and `tools/../docs/x`"), ["../a/b"])


class Corpus(Tree):
    def test_readmes_rubrics_and_indexes_are_never_slices_whatever_their_front_matter_says(self):
        for name in ("README.md", "RUBRIC.md", "INDEX.md"):
            self.write(f"memory/domains/d/{name}", slice_text(("s", "`tools/fabric/deleted.py`")))
        self.write("memory/domains/d/domain/emptyclass.md", "---\nclass:\n---\n\n## s\n\n`tools/fabric/deleted.py`\n")
        self.assertEqual(self.report()["sections"], [])

    def test_only_slices_with_a_class_other_than_index_are_read(self):
        self.write("memory/README.md", "# r\n\n## s\n\n`tools/fabric/deleted.py`\n")
        self.write("memory/domains/d/INDEX.md", slice_text(("s", "`tools/fabric/deleted.py`"), klass="index"))
        self.write("memory/domains/d/domain/nofront.md", "## s\n\n`tools/fabric/deleted.py`\n")
        self.slice("real", ("s", "`tools/fabric/deleted.py`"), klass="solution")
        self.assertEqual(self.verdicts(), {("real.md", "s"): "stale-hard"})

    def test_a_working_copys_corpus_is_checked_in_the_working_copy(self):
        wc = os.path.join(self.base, "proj")
        self.write("src/app.rs", "x", root=wc)
        self.write(".agent-fabric/memory/r/solution/s.md", slice_text(("s", "`src/app.rs` and `src/gone.rs`"), klass="solution"), root=wc)
        r = self.run_cli(os.path.join(wc, ".agent-fabric", "memory"), "--json")
        doc = json.loads(r.stdout)
        self.assertEqual(doc["tree"], wc)
        self.assertEqual([(p["path"], p["status"]) for p in doc["sections"][0]["paths"]], [("src/app.rs", "exists"), ("src/gone.rs", "stale-hard")])

    def test_a_root_that_is_not_a_memory_directory_needs_its_tree_named(self):
        odd = os.path.join(self.base, "odd")
        os.makedirs(odd)
        r = self.run_cli(odd)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("name the tree its paths belong to with --tree", r.stderr)
        self.write("x.md", slice_text(("s", "`tools/fabric/layout.py`")), root=odd)
        ok = self.run_cli(odd, "--tree", self.tree, "--json")
        self.assertEqual(json.loads(ok.stdout)["sections"][0]["verdict"], "fresh")

    def test_no_corpus_and_no_tree_are_refusals_in_one_line(self):
        for args in ([os.path.join(self.base, "nothing", "memory")], [self.corpus, "--tree", os.path.join(self.base, "nowhere")]):
            r = self.run_cli(*args)
            self.assertEqual((r.returncode, r.stdout), (2, ""), args)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1)
            self.assertTrue(r.stderr.startswith("fabric-memory-check: "))

    def test_nothing_is_written_to_the_corpus_or_the_tree(self):
        self.slice("a", ("s", "`tools/fabric/deleted.py`"))
        before = sorted((d, f, os.stat(os.path.join(d, f)).st_mtime_ns) for d, _, fs in os.walk(self.base) for f in fs)
        self.run_cli(self.corpus)
        self.run_cli(self.corpus, "--json", "--all")
        after = sorted((d, f, os.stat(os.path.join(d, f)).st_mtime_ns) for d, _, fs in os.walk(self.base) for f in fs)
        self.assertEqual(before, after)


GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}


def git(tree: str, *args: str, date: str | None = None) -> str:
    env = {**GIT_ENV, **({"GIT_AUTHOR_DATE": f"{date}T12:00:00Z", "GIT_COMMITTER_DATE": f"{date}T12:00:00Z"} if date else {})}
    r = subprocess.run(["git", "-C", tree, "-c", "user.name=t", "-c", "user.email=t@example.test", "-c", "commit.gpgsign=false", *args],
                       capture_output=True, text=True, env=env, timeout=60, check=True, stdin=subprocess.DEVNULL)
    return r.stdout.strip()


def anchored(body: str, anchors: list[str], observed: str | None = "2026-03-10", role: str = "python-dev") -> str:
    """A section's text as the assembler writes it: the body, the Anchors line, the Observed tail."""
    return (body + ("\n\n*Anchors: " + ", ".join(f"`{x}`" for x in anchors) + "*" if anchors else "")
            + (f"\n\n*Observed {observed} ({role})*" if observed else ""))


class Anchors(Tree):
    """ADR-050 rules 1 and 2: anchors, the symbol they name, and a change since the section was written."""

    def setUp(self):
        super().setUp()
        git(self.tree, "init", "-q")
        self.write("tools/fabric/runner.py", "def run_it():\n    return 1\n")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "the first state", date="2026-03-01")

    def verdicts(self, *args):
        return {s["heading"]: s for s in self.report(*args)["sections"]}

    def test_an_anchor_that_holds_and_whose_file_has_not_moved_is_fresh_and_silent(self):
        self.slice("a", ("ok", anchored("Body.", ["tools/fabric/runner.py::run_it"])))
        row = self.verdicts()["ok"]
        self.assertEqual((row["verdict"], row["anchors"][0]["status"], row["observed"], row["role"]), ("fresh", "exists", "2026-03-10", "python-dev"))
        self.assertNotIn("ok", self.run_cli(self.corpus).stdout.replace("summary", ""), "a fresh section is not listed without --all")

    def test_a_path_that_is_gone_a_symbol_that_is_gone_and_a_directory_with_a_symbol_are_stale_hard(self):
        self.slice("a", ("path", anchored("B.", ["tools/fabric/deleted.py::run_it"])),
                   ("symbol", anchored("B.", ["tools/fabric/runner.py::renamed_it"])),
                   ("dir", anchored("B.", ["tools/fabric::run_it"])),
                   ("whole", anchored("B.", ["tools/fabric/runner.py"])))
        v = self.verdicts()
        self.assertEqual({h: v[h]["verdict"] for h in v}, {"path": "stale-hard", "symbol": "stale-hard", "dir": "stale-hard", "whole": "fresh"})
        self.assertIn("renamed_it", v["symbol"]["anchors"][0]["why"])
        out = [ln.split("\t") for ln in self.run_cli(self.corpus).stdout.splitlines()]
        self.assertIn(["stale-hard", "domains/d/domain/a.md", "symbol", "tools/fabric/runner.py::renamed_it",
                       "the file no longer holds 'renamed_it'"], out)
        self.assertIn(["stale-hard", "domains/d/domain/a.md", "path", "tools/fabric/deleted.py::run_it"], out)

    def test_a_file_changed_after_the_observed_day_is_maybe_stale_and_names_the_commit(self):
        self.write("tools/fabric/runner.py", "def run_it():\n    return 2\n")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "the run changes its answer", date="2026-03-20")
        want = git(self.tree, "rev-parse", "--short", "HEAD")
        self.slice("a", ("moved", anchored("B.", ["tools/fabric/runner.py::run_it"], observed="2026-03-10")),
                   ("later", anchored("B.", ["tools/fabric/runner.py::run_it"], observed="2026-03-25")),
                   ("sameday", anchored("B.", ["tools/fabric/runner.py::run_it"], observed="2026-03-20")))
        v = self.verdicts()
        self.assertEqual({h: v[h]["verdict"] for h in v}, {"moved": "maybe-stale", "later": "fresh", "sameday": "fresh"})
        a = v["moved"]["anchors"][0]
        self.assertEqual((a["commit"], a["date"], a["subject"]), (want, "2026-03-20", "the run changes its answer"))
        out = [ln.split("\t") for ln in self.run_cli(self.corpus).stdout.splitlines()]
        self.assertIn(["maybe-stale", "domains/d/domain/a.md", "moved", "tools/fabric/runner.py::run_it", f"{want} 2026-03-20 the run changes its answer"], out)

    def test_stale_hard_outranks_maybe_stale_outranks_unchecked_outranks_fresh(self):
        self.write("tools/fabric/runner.py", "def run_it():\n    return 2\n")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "moved", date="2026-03-20")
        self.slice("a", ("all", anchored("B. `tools/fabric/deleted.py`", ["tools/fabric/runner.py::run_it", "tools/fabric/layout.py"])),
                   ("movedfresh", anchored("B.", ["tools/fabric/runner.py::run_it", "tools/fabric/layout.py"])),
                   ("uncheckedfresh", anchored("B.", ["tools/fabric/layout.py"], observed="2026-03-25") + "\n\n`../zz/y/z`"))
        v = self.verdicts()
        self.assertEqual({h: v[h]["verdict"] for h in v}, {"all": "stale-hard", "movedfresh": "maybe-stale", "uncheckedfresh": "unchecked"})

    def test_history_that_cannot_be_read_is_unchecked_never_stale_and_never_fresh(self):
        self.slice("a", ("s", anchored("B.", ["tools/fabric/runner.py::run_it"])))
        # not a repository
        shutil.rmtree(os.path.join(self.tree, ".git"))
        row = self.verdicts()["s"]
        self.assertEqual((row["verdict"], row["anchors"][0]["status"]), ("unchecked", "unchecked"))
        self.assertIn("no git history", row["anchors"][0]["why"])
        # git not installed
        r = self.run_cli(self.corpus, "--json", env={"PATH": "/nonexistent"})
        self.assertEqual(json.loads(r.stdout)["sections"][0]["verdict"], "unchecked")
        # a shallow clone
        origin = self.tree + "-origin"
        shutil.copytree(self.tree, origin, ignore=shutil.ignore_patterns("memory"))
        git(origin, "init", "-q")
        git(origin, "add", "-A")
        git(origin, "commit", "-q", "-m", "one", date="2026-03-01")
        self.write("tools/fabric/runner.py", "def run_it():\n    return 3\n", root=origin)
        git(origin, "commit", "-q", "-am", "two", date="2026-03-02")
        shutil.rmtree(self.tree)
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + origin, self.tree], check=True, env=GIT_ENV, capture_output=True, timeout=60)
        self.slice("a", ("s", anchored("B.", ["tools/fabric/runner.py::run_it"])))
        row = self.verdicts()["s"]
        self.assertEqual(row["verdict"], "unchecked")
        self.assertIn("shallow", row["anchors"][0]["why"])

    def test_anchors_with_no_observed_date_cannot_be_judged_for_a_change(self):
        self.slice("a", ("undated", anchored("B.", ["tools/fabric/runner.py::run_it"], observed=None)),
                   ("gone", anchored("B.", ["tools/fabric/deleted.py"], observed=None)))
        v = self.verdicts()
        self.assertEqual((v["undated"]["verdict"], v["gone"]["verdict"]), ("unchecked", "stale-hard"))
        self.assertIn("no Observed date", v["undated"]["why"])
        self.assertIn(["unchecked", "domains/d/domain/a.md", "undated", "-", v["undated"]["why"]],
                      [ln.split("\t") for ln in self.run_cli(self.corpus).stdout.splitlines()])

    def test_an_anchor_in_an_origin_projects_checkout_is_judged_there_by_that_checkouts_history(self):
        other = os.path.join(self.base, "other")
        os.makedirs(os.path.join(other, "src"))
        git(other, "init", "-q")
        self.write("src/engine.py", "class Engine: ...\n", root=other)
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "engine v1", date="2026-03-01")
        self.write("src/engine.py", "class Engine:\n    pass\n", root=other)
        git(other, "commit", "-q", "-am", "engine v2", date="2026-03-20")
        self.slice("a", ("far", anchored("B.", ["src/engine.py::Engine"])), origins=(("other", "other"),))
        row = self.verdicts("--project", "agent-fabric")["far"]
        self.assertEqual((row["verdict"], row["anchors"][0]["subject"]), ("maybe-stale", "engine v2"))

    def test_a_file_too_large_to_search_is_unchecked_not_stale(self):
        self.slice("a", ("big", anchored("B.", ["tools/fabric/runner.py::run_it"])))
        orig = memory_check.ANCHOR_FILE_MAX
        memory_check.ANCHOR_FILE_MAX = 10
        try:
            row = memory_check.check(self.corpus, self.tree)[0]
        finally:
            memory_check.ANCHOR_FILE_MAX = orig
        self.assertEqual((row["verdict"], row["anchors"][0]["status"]), ("unchecked", "unchecked"))
        self.assertIn("larger than 10 bytes", row["anchors"][0]["why"])
        self.assertEqual(memory_check.check(self.corpus, self.tree)[0]["verdict"], "fresh", "positive control: within the bound it is searched")

    def test_the_history_asks_git_with_an_argument_list_a_timeout_and_a_minimal_environment(self):
        calls = []

        class Done:
            def __init__(self, out, rc=0):
                self.stdout, self.stderr, self.returncode = out, "", rc

        def fake(argv, **kw):
            calls.append((argv, kw))
            return Done("false\n" if "rev-parse" in argv else "abc1234\t2026-03-20\tsubject\n")
        h = memory_check.History(run=fake)
        self.assertEqual(h.changed_after("/t", "a/b.py", "2026-03-10"), {"commit": "abc1234", "date": "2026-03-20", "subject": "subject"})
        self.assertEqual(len(calls), 2)
        for argv, kw in calls:
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[:3], ["git", "-C", "/t"])
            self.assertEqual(kw["timeout"], memory_check.GIT_TIMEOUT_S)
            self.assertFalse(kw.get("shell"))
            self.assertNotIn("GIT_DIR", kw["env"])
            self.assertEqual(kw["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertTrue(any(a.startswith("--since=") and a.endswith(" +0000") for a in calls[1][0]), calls[1][0])
        self.assertEqual(calls[1][0][-2:], ["--", "a/b.py"], "the path follows `--`, never read as an option")
        # a timeout and a failing git are unknown, not an exception out of the check
        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaises(memory_check.NoHistory):
            memory_check.History(run=slow).changed_after("/t", "a", "2026-03-10")
        with self.assertRaises(memory_check.NoHistory):
            memory_check.History(run=lambda argv, **kw: Done("", 128)).changed_after("/t", "a", "2026-03-10")


class Output(Tree):
    def setUp(self):
        super().setUp()
        self.slice("a", ("gone", "`tools/fabric/deleted.py`"), ("fine", "`tools/fabric/layout.py`"), ("none", "prose"), ("far", "`../zz/y/z`"))

    def test_the_lines_are_findings_then_a_summary_and_the_exit_is_zero(self):
        r = self.run_cli(self.corpus)
        self.assertEqual(r.returncode, 0, "a report, not a gate")
        out = r.stdout.splitlines()
        self.assertEqual(out[0].split("\t"), ["stale-hard", "domains/d/domain/a.md", "gone", "tools/fabric/deleted.py"])
        self.assertEqual(out[1].split("\t"), ["unchecked", "domains/d/domain/a.md", "far", "../zz/y/z", "no checkout 'zz' beside the tree"])
        self.assertEqual(out[2], "summary\t1 stale-hard, 0 maybe-stale, 1 unchecked, 1 fresh, 1 no-anchor, 0 unreadable; 1 slice(s) cite a path that is gone")
        self.assertEqual(len(out), 3)

    def test_all_adds_the_fresh_and_no_anchor_sections(self):
        out = [ln.split("\t") for ln in self.run_cli(self.corpus, "--all").stdout.splitlines()]
        self.assertIn(["fresh", "domains/d/domain/a.md", "fine", "1 path(s)"], out)
        self.assertIn(["no-anchor", "domains/d/domain/a.md", "none"], out)

    def test_json_is_one_document_with_every_section_and_the_counts(self):
        doc = self.report()
        self.assertEqual(sorted(doc), ["corpus", "counts", "sections", "tree"])
        self.assertEqual(doc["counts"], {"stale-hard": 1, "maybe-stale": 0, "unchecked": 1, "fresh": 1, "no-anchor": 1, "unreadable": 0})
        self.assertEqual(doc["tree"], self.tree)
        self.assertEqual([s["heading"] for s in doc["sections"]], ["gone", "fine", "none", "far"])

    def test_usage_errors_are_two_with_one_stderr_line(self):
        for args in (["--nope"], ["a", "b"], ["--tree"]):
            r = self.run_cli(*args)
            self.assertEqual((r.returncode, r.stdout), (2, ""), args)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1, args)

    def test_help_is_the_modules_text_and_exit_zero(self):
        r = self.run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("fabric-memory-check [CORPUS]", r.stdout)

    def test_the_installed_entry_point_runs_the_module_and_names_a_missing_python(self):
        ok = self.run_cli(self.corpus, "--json", entry=BIN, env={"AGENT_FABRIC_PYTHON": sys.executable})
        self.assertEqual((ok.returncode, json.loads(ok.stdout)["counts"]["stale-hard"]), (0, 1))
        bad = self.run_cli(self.corpus, entry=BIN, env={"AGENT_FABRIC_PYTHON": "/nonexistent/python"})
        self.assertEqual(bad.returncode, 127)
        self.assertIn("fabric-memory-check: the fleet's pinned Python is not installed", bad.stderr)

    def test_the_module_is_importable_and_check_returns_the_rows(self):
        rows = memory_check.check(self.corpus, self.tree)
        self.assertEqual([r["verdict"] for r in rows], ["stale-hard", "fresh", "no-anchor", "unchecked"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
