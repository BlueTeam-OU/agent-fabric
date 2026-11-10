#!/usr/bin/env python3
"""ADR-068 §5 rule 7: a hook that recognises a fabric command decides the same for `fabric-pr …` and `fabric pr …`.
post-review-shape-guard.py and job-copy-guard.py are the two that did by name when the record was written.

Stdlib only; runnable as `python3 tests/test_fabric_spellings.py`. Each pair is the same command in its two spellings
(the second is the first with `fabric-pr ` read as `fabric pr `), the decision of the first is pinned so that two
silent guards cannot agree, and the pairs hold both verdicts so that a guard that refuses everything or nothing fails.
**Mutations it kills**: a guard keeping its own pattern for `fabric-pr` (the second spelling walks past it), and one that
reads only the dispatcher spelling.

Both guards read the checkout's commands.json for the `fabric` table: the cases are red until that table and the guards'
move onto tools/fabric/cli canonical() have landed (fabric-coordinator's commits on this pull request)."""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_job_copy_guard as tj  # noqa: E402

ROOT = os.path.dirname(HERE)
SHAPE_HOOK = os.path.join(ROOT, "runtime", "claude-code", "hooks", "post-review-shape-guard.py")


def respelled(cmd: str) -> str:
    return cmd.replace("fabric-pr ", "fabric pr ")


class PostReviewShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("post_review_shape_guard", SHAPE_HOOK)
        cls.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.guard)

    CASES = [
        ("bare", "fabric-pr post-review 12 < r.md", False),
        ("with options", "fabric-pr post-review --repo o/n --model fable 12 < r.md", False),
        ("by path", "bin/fabric-pr post-review 12 < r.md", True),
        ("a pipe", "fabric-pr post-review 12 < r.md | tail -3", True),
        ("2>&1", "fabric-pr post-review 12 < r.md 2>&1", True),
        ("a command first", "cd /x && fabric-pr post-review 12 < r.md", True),
        ("an env assignment", "LC_ALL=C fabric-pr post-review 12 < r.md", True),
        ("timeout", "timeout 60 fabric-pr post-review 12 < r.md", True),
        ("bash -c", 'bash -c "fabric-pr post-review 12 < r.md"', True),
        ("a heredoc", "fabric-pr post-review 12 <<'EOF'\nreport\nEOF", True),
        ("a substitution", "out=$(fabric-pr post-review 12 < r.md)", True),
        ("a mention", "echo fabric-pr post-review", True),
        ("another verb", "fabric-pr gate 12", False),
    ]

    def test_both_spellings_decide_alike(self):
        for label, cmd, refused in self.CASES:
            with self.subTest(case=label):
                self.assertEqual(self.guard.refused(cmd), refused, f"the pinned decision for {cmd!r}")
                self.assertEqual(self.guard.refused(respelled(cmd)), refused, respelled(cmd))

    def test_the_verdicts_are_not_one_sided(self):
        self.assertTrue({v for _, _, v in self.CASES} == {True, False})


class JobCopy(tj.Guard):
    """The job-copy guard's world (a job active in `proj`, its worktree, other working copies), reused for the pairs below.
    The parent's own cases are not repeated here: they are set to None, which unittest does not collect."""

    PAIRS = [
        ("a write to another working copy", "cd {other} && fabric-pr arm 12", "deny"),
        ("a read of the gate", "fabric-pr gate", "allow"),
        ("a repository of another project", "fabric-pr --repo acme/other arm 12", "deny"),
        ("the job's own repository", "fabric-pr --repo acme/proj arm 12", "allow"),
        ("a post-review read from a report", "fabric-pr post-review 5 < r.md", "allow"),
    ]

    def test_both_spellings_decide_alike(self):
        self.active_j7()
        for label, template, want in self.PAIRS:
            cmd = template.format(other=self.other)
            for spelled in (cmd, respelled(cmd), cmd.replace("fabric-pr ", "bin/fabric-pr ")):
                with self.subTest(case=label, command=spelled):
                    self.assertEqual(self.decision(spelled, self.worktree), want)

    def test_the_verdicts_are_not_one_sided(self):
        self.assertTrue({w for _, _, w in self.PAIRS} == {"allow", "deny"})


for _name in [n for n in dir(tj.Guard) if n.startswith("test")]:
    setattr(JobCopy, _name, None)
JobCopy.test_both_spellings_decide_alike = JobCopy.__dict__["test_both_spellings_decide_alike"]
JobCopy.test_the_verdicts_are_not_one_sided = JobCopy.__dict__["test_the_verdicts_are_not_one_sided"]
del tj.Guard   # the parent is not collected a second time from this module

if __name__ == "__main__":
    sys.exit(unittest.main())
