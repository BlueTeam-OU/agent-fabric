#!/usr/bin/env python3
"""tools/fabric/guards/commit_kind.py's argv walk: what counts as
`git commit --amend` when the hook reads the argv of the git that runs it
(review of #120: a word match exempted `commit -m --amend`)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "guards"))
import commit_kind  # noqa: E402

CASES = [
    (["git", "commit", "--amend", "--no-edit"], True, "the flag"),
    (["/usr/bin/git", "commit", "--amen", "--no-edit"], True, "a unique prefix"),
    (["git", "commit", "--am"], True, "the shortest unique prefix"),
    (["git", "-C", "/r", "-c", "k=v", "commit", "--amend"], True, "global options with values before the subcommand"),
    (["git", "commit", "-m", "--amend"], False, "--amend as -m's value"),
    (["git", "commit", "-m", "x", "-m", "--amend"], False, "as a second -m's value"),
    (["git", "commit", "-am", "--amend"], False, "as the value ending a short cluster"),
    (["git", "commit", "--message", "--amend"], False, "as --message's value"),
    (["git", "commit", "--message=--amend"], False, "attached to --message"),
    (["git", "commit", "-m--amend"], False, "attached to -m"),
    (["git", "commit", "--", "--amend"], False, "a pathspec after --"),
    (["git", "commit", "-q", "-C", "HEAD"], False, "-C HEAD reuses a message, it does not amend"),
    (["git", "commit", "-C", "--amend"], False, "-C's value"),
    (["git", "-C", "commit", "status", "--amend"], False, "another subcommand"),
    (["git", "commit", "--a"], False, "an ambiguous prefix"),
    (["git"], False, "no subcommand"),
]


def main() -> int:
    fails = 0
    for argv, want, label in CASES:
        got = commit_kind.is_amend(argv)
        ok = got is want
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: {' '.join(argv[1:])} -> {got}")
    print(f"{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
