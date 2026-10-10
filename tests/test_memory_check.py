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
FRONT = '---\nrole: "r"\nclass: {klass}\ntopic: "t"\n---\n\n'


def slice_text(*sections: tuple[str, str], klass: str = "domain") -> str:
    return FRONT.format(klass=klass) + "\n".join(f"## {h}\n\n{b}\n" for h, b in sections)


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

    def slice(self, name, *sections, klass="domain"):
        return self.write(f"memory/domains/d/domain/{name}.md", slice_text(*sections, klass=klass))

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


class Output(Tree):
    def setUp(self):
        super().setUp()
        self.slice("a", ("gone", "`tools/fabric/deleted.py`"), ("fine", "`tools/fabric/layout.py`"), ("none", "prose"), ("far", "`../zz/y/z`"))

    def test_the_lines_are_findings_then_a_summary_and_the_exit_is_zero(self):
        r = self.run_cli(self.corpus)
        self.assertEqual(r.returncode, 0, "a report, not a gate")
        out = r.stdout.splitlines()
        self.assertEqual(out[0].split("\t"), ["stale-hard", "domains/d/domain/a.md", "gone", "tools/fabric/deleted.py"])
        self.assertEqual(out[1].split("\t"), ["unchecked", "domains/d/domain/a.md", "far", "../zz/y/z"])
        self.assertEqual(out[2], "summary\t1 stale-hard, 1 unchecked, 1 fresh, 1 no-anchor; 1 slice(s) cite a path that is gone")
        self.assertEqual(len(out), 3)

    def test_all_adds_the_fresh_and_no_anchor_sections(self):
        out = [ln.split("\t") for ln in self.run_cli(self.corpus, "--all").stdout.splitlines()]
        self.assertIn(["fresh", "domains/d/domain/a.md", "fine", "1 path(s)"], out)
        self.assertIn(["no-anchor", "domains/d/domain/a.md", "none"], out)

    def test_json_is_one_document_with_every_section_and_the_counts(self):
        doc = self.report()
        self.assertEqual(sorted(doc), ["corpus", "counts", "sections", "tree"])
        self.assertEqual(doc["counts"], {"stale-hard": 1, "unchecked": 1, "fresh": 1, "no-anchor": 1})
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
