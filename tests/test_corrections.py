#!/usr/bin/env python3
"""tools/fabric/corrections.py (ADR-050 rule 10): one key for a memory's body and for the corpus section it became."""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from corrections import applied_stems, demote_headings, memory_key, names_in, point_text, section_key, unique_stems  # noqa: E402


class BodyKey(unittest.TestCase):
    def test_the_tail_lines_a_section_carries_are_not_part_of_the_text(self):
        body = "The fact, in words."
        section = body + "\n\n*References: a, b*\n\n*Anchors: `tools/a.py::run`*\n\n*Observed 2026-10-01 (python-dev)*\n"
        self.assertEqual(section_key(section), section_key(body))
        self.assertEqual(section_key(body + "\n\n*Observed 2026-01-01*"), section_key(body))

    def test_a_tail_line_in_the_middle_of_the_text_is_text(self):
        text = "Before.\n\n*Observed 2026-10-01 (x)*\n\nAfter."
        self.assertNotEqual(section_key(text), section_key("Before.\n\nAfter."))

    def test_an_italic_line_that_only_starts_like_a_tail_is_text(self):
        self.assertNotEqual(section_key("Fact.\n\n*Observed on staging only*"), section_key("Fact."))
        self.assertNotEqual(section_key("Fact.\n\n*References are in the ticket*"), section_key("Fact."))
        self.assertEqual(section_key("Fact.\n\n*Observed 2026-10-01*"), section_key("Fact."))      # the control: the real tail

    def test_wrapping_and_spacing_are_not_part_of_the_text(self):
        self.assertEqual(section_key("one two\n   three\tfour\n\n\nfive"), section_key("one two three four five"))

    def test_body_headings_are_compared_as_the_assembler_demotes_them(self):
        # a memory with a "## Sub" heading becomes a section holding "### Sub": one key, not two (demoted once)
        self.assertEqual(memory_key("Text\n\n## Sub\n\nmore"), section_key("Text\n\n### Sub\n\nmore"))
        self.assertNotEqual(section_key("Text\n\n### Sub\n\nmore"), section_key("Text\n\n#### Sub\n\nmore"))
        self.assertEqual(demote_headings("# Top\n## Two\n#### Four\ntext ## not a heading"), "# Top\n### Two\n##### Four\ntext ## not a heading")

    def test_another_word_is_another_text_and_the_key_is_stable_and_short(self):
        self.assertNotEqual(memory_key("The old fact."), memory_key("The new fact."))
        self.assertEqual(section_key("x"), section_key("x"))
        self.assertRegex(section_key("x"), r"^[0-9a-f]{16}$")
        self.assertEqual(section_key(""), section_key("  \n"))


class Pointing(unittest.TestCase):
    ENTRIES = [{"memory": "m", "slice": ".agent-fabric/memory/architect-cto/solution.md"},
               {"memory": "s", "slice": "memory/domains/shared/domain/topic.md"},
               {"memory": "bad"}, "junk"]

    def test_a_stem_comes_from_the_slice_path_and_the_role_from_its_directory(self):
        self.assertEqual(applied_stems(self.ENTRIES), [("architect-cto", "m", "solution"), (None, "s", "topic")])

    def test_a_name_two_stems_claim_is_left_as_written_and_a_name_that_is_its_stem_is_not_moved(self):
        found = [("r", "a", "one"), ("r", "a", "two"), ("r", "b", "b"), ("r", "c", "three"), (None, "c", "four")]
        unique = unique_stems(found)
        self.assertEqual(unique, {("r", "c"): "three", (None, "c"): "four"})
        self.assertEqual(names_in(unique, ("r",)), {"c": "three"})

    def test_links_and_the_references_line_are_pointed_and_other_text_is_not(self):
        text = "See [[m]] and [[mm]].\n\n*References: m, other*"
        self.assertEqual(point_text(text, {"m": "solution"}), "See [[solution]] and [[mm]].\n\n*References: other, solution*")
        self.assertEqual(point_text(text, {}), text)


if __name__ == "__main__":
    unittest.main()
