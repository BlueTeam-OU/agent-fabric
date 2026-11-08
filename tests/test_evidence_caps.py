#!/usr/bin/env python3
"""tools/fabric/evidence_caps.py: GitHub's list caps and the reads they cut have one owner, github/evidence.py (j119).
Stdlib only; runnable as `python3 tests/test_evidence_caps.py`. **Each case names the mutation it kills**:

  planted_cap_in_arm        <- CAPS emptied, or _cap's Assign / Compare branch dropped
  caps_are_the_two          <- CAPS widened to every integer (500 flagged), or one of the two dropped
  read_is_found             <- PR_LIST_PATH narrowed to the paginated form, or the list-argument walk dropped
  owners_and_others_pass    <- OWNERS not exempt, or a module outside github/ (or in a subdirectory) judged
  the_tree_is_clean         <- a cap or a files/commits read left in tools/fabric/github/ outside the two owners
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import evidence_caps as ec  # noqa: E402

ARM = "tools/fabric/github/arm.py"


class Caps(unittest.TestCase):
    def test_planted_cap_in_arm(self):
        with open(os.path.join(HERE, ARM), encoding="utf-8") as fh:
            real = fh.read()
        self.assertEqual(ec.scan(ARM, real), [])   # the positive control: the module as it is, is clean
        planted = real + "\nPR_COMMITS_CAP = 250\n"
        got = ec.scan(ARM, planted)
        self.assertEqual(len(got), 1, got)
        self.assertIn("cap:", got[0])
        self.assertEqual(len(ec.scan(ARM, real + "\nx = len([]) >= 3000\n")), 1)

    def test_caps_are_the_two(self):
        self.assertEqual(len(ec.scan(ARM, "A = 250\nB = 3000\n")), 2)
        self.assertEqual(ec.scan(ARM, "A = 500\nB = 200\nC = '250'\nD = 250.0\nE = True\nF = 2500\n"), [])

    def test_read_is_found(self):
        for src in ('gh.api(f"repos/{r}/pulls/{n}/files?per_page=100", paginate=True)',
                    'gh.api_list(f"repos/{r}/pulls/{n}/commits")',
                    'gh.run(["api", "--paginate", "--slurp", f"repos/{r}/pulls/{n}/commits?per_page=100"])',
                    'gh.api("repos/o/r/pulls/7/files")'):
            with self.subTest(src=src):
                got = ec.scan(ARM, src + "\n")
                self.assertEqual(len(got), 1, got)
                self.assertIn("read:", got[0])
        # Other pull-request reads and other lists are not this rule's.
        for src in ('gh.api(f"repos/{r}/pulls/{n}/reviews?per_page=100", paginate=True)',
                    'gh.api(f"repos/{r}/commits?since=x", paginate=True)',
                    'gh.api(f"repos/{r}/pulls/{n}/comments")'):
            with self.subTest(src=src):
                self.assertEqual(ec.scan(ARM, src + "\n"), [])

    def test_owners_and_others_pass(self):
        src = "A = 250\ngh.api('repos/o/r/pulls/7/files')\n"
        self.assertEqual(len(ec.scan(ARM, src)), 2)   # the positive control
        for rel in ("tools/fabric/github/common.py", "tools/fabric/github/evidence.py", "tools/fabric/gh.py",
                    "tools/fabric/github/review_status/base.py", "tests/test_x.py", "tools/fabric/github/x.sh"):
            with self.subTest(rel=rel):
                self.assertEqual(ec.scan(rel, src), [])
        self.assertEqual(ec.scan(ARM, "def ("), [])   # a syntax error is the compiler's

    def test_the_tree_is_clean(self):
        self.assertEqual(ec.findings(HERE), [])


if __name__ == "__main__":
    unittest.main()
