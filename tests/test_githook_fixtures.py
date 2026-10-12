#!/usr/bin/env python3
"""tests/githook_fixtures.py: the guard of Repo.write, which keeps every scratch file inside the scratch root. A scratch fabric root
links the real runtime/ and tools/fabric/ entries (Fabric); a test that stages a path beneath such a link would write into the checkout,
so the write is refused - and refused BEFORE any directory is made, which is what this file pins (review of #230, F2: the guard once
ran after os.makedirs, so the refusal itself created the directory in the checkout).

Mutation it fails on: moving the realpath check after `os.makedirs` (the case that stages under the linked runtime/ finds the directory
the refusal created)."""
from __future__ import annotations

import os
import shutil
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import ROOT, Fabric, Repo  # noqa: E402


class Guard(unittest.TestCase):
    def test_a_write_beneath_a_link_into_the_checkout_is_refused_and_creates_nothing_there(self):
        fabric = Fabric()
        self.addCleanup(fabric.cleanup)
        repo = fabric.itself()
        name = "scratch-guard-" + uuid.uuid4().hex                      # a name no checkout holds
        outside = os.path.join(ROOT, "runtime", name)
        self.addCleanup(shutil.rmtree, outside, True)                   # should the guard ever fail, leave no residue
        for rel in (f"runtime/{name}/x.txt", f"runtime/{name}/deep/er/y.txt"):
            with self.subTest(rel=rel):
                with self.assertRaises(AssertionError) as caught:
                    repo.write(rel, "x\n")
                self.assertIn("resolves outside the scratch root", str(caught.exception))
                self.assertFalse(os.path.lexists(outside), "the refusal created a directory in the checkout")

    def test_the_same_guard_covers_a_link_to_a_file_and_a_path_that_climbs_out(self):
        fabric = Fabric()
        self.addCleanup(fabric.cleanup)
        repo = fabric.itself()
        for rel in ("tools/fabric/layout.py", "../../escaped.txt"):          # the scratch root is the fabric's PARENT: two levels leave it
            with self.subTest(rel=rel):
                before = os.stat(os.path.join(ROOT, "tools/fabric/layout.py")).st_mtime_ns
                with self.assertRaises(AssertionError):
                    repo.write(rel, "x\n", append=True)
                self.assertEqual(os.stat(os.path.join(ROOT, "tools/fabric/layout.py")).st_mtime_ns, before)
                self.assertFalse(os.path.exists(os.path.join(os.path.dirname(fabric.root), "escaped.txt")))

    def test_a_path_inside_the_scratch_root_is_written(self):
        repo = Repo({"README": "r\n"})
        self.addCleanup(repo.cleanup)
        repo.write("a/b/c.txt", "ok\n")
        with open(os.path.join(repo.path, "a/b/c.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "ok\n")


if __name__ == "__main__":
    unittest.main()
